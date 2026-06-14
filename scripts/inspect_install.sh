#!/bin/bash
# PRADY OS — OFFLINE installed-disk inspector (host side, Linux/WSL).
#
#   sudo bash scripts/inspect_install.sh <disk.(qcow2|img|raw)>
#
# The companion to scripts/verify_install.sh. Where verify_install.sh *boots* the
# installed disk in QEMU (the strong, end-to-end gate), this script *inspects* the
# disk image offline by loop-mounting it — fast, no VM — and asserts the install
# actually landed: a GPT layout (BIOS-boot + ESP + ext4 root), a PradyOS rootfs,
# a real /boot with kernel + initramfs + grub.cfg, and a populated ESP. This is
# the "inspect via losetup" pass: it answers "did pradyos-install write a bootable
# system to the disk?" in seconds, and pinpoints WHICH artefact is missing.
#
#   * RAW/.img  → losetup -P (kernel partition scan).
#   * .qcow2    → qemu-nbd  (needs nbd kernel module + qemu-utils).
#
# Tunables (env): PRADYOS_NBD (/dev/nbd0), PRADYOS_INSPECT_MNT (mktemp).
# Exit 0 + "PRADYOS-INSPECT: PASS" on success; non-zero + "...: FAIL <why>" else.
set -euo pipefail

IMG="${1:-}"
NBD="${PRADYOS_NBD:-/dev/nbd0}"
MNT="${PRADYOS_INSPECT_MNT:-$(mktemp -d /tmp/pradyos-inspect.XXXXXX)}"
ROOTMNT="$MNT/root"; ESPMNT="$MNT/esp"
LOOPDEV=""; USED_NBD=0; FAILED=0

c_ok="\033[1;32m"; c_no="\033[1;31m"; c_in="\033[1;36m"; c_z="\033[0m"
log()  { echo -e "${c_in}[inspect]${c_z} $*"; }
ok()   { echo -e "  ${c_ok}✓${c_z} $*"; }
bad()  { echo -e "  ${c_no}✗${c_z} $*"; FAILED=1; }
die()  { echo -e "${c_no}[inspect] FAIL:${c_z} $*" >&2; echo "PRADYOS-INSPECT: FAIL $*"; exit 1; }

[ -n "$IMG" ] || die "usage: inspect_install.sh <disk.(qcow2|img|raw)>"
[ -f "$IMG" ] || die "image not found: $IMG"
[ "$(id -u)" -eq 0 ] || die "must run as root (loop-mounting needs privileges)"
command -v lsblk >/dev/null || die "lsblk not installed"

cleanup() {
    mountpoint -q "$ESPMNT"  2>/dev/null && umount "$ESPMNT"  || true
    mountpoint -q "$ROOTMNT" 2>/dev/null && umount "$ROOTMNT" || true
    if [ "$USED_NBD" = 1 ]; then qemu-nbd --disconnect "$NBD" >/dev/null 2>&1 || true; fi
    [ -n "$LOOPDEV" ] && losetup -d "$LOOPDEV" 2>/dev/null || true
    rm -rf "$MNT" 2>/dev/null || true
}
trap cleanup EXIT
mkdir -p "$ROOTMNT" "$ESPMNT"

# ---- attach the image, exposing its partitions -------------------------------
case "$IMG" in
    *.qcow2|*.qed|*.vmdk|*.vdi)
        command -v qemu-nbd >/dev/null || die "qemu-nbd not installed (apt install qemu-utils)"
        modprobe nbd max_part=8 2>/dev/null || true
        log "attaching $IMG via qemu-nbd ($NBD)"
        qemu-nbd --connect="$NBD" "$IMG" || die "qemu-nbd connect failed"
        USED_NBD=1; sleep 1; partprobe "$NBD" 2>/dev/null || true
        DEV="$NBD"; P="p"
        ;;
    *)
        log "attaching $IMG via losetup -P"
        LOOPDEV="$(losetup --show -fP "$IMG")" || die "losetup failed"
        DEV="$LOOPDEV"; P="p"
        ;;
esac
udevadm settle 2>/dev/null || true; sleep 1

# ---- partition table -----------------------------------------------------------
log "partition layout on $DEV"
lsblk -no NAME,SIZE,FSTYPE,LABEL "$DEV" 2>/dev/null | sed 's/^/    /' || true
NPARTS="$(lsblk -rno NAME "$DEV" | grep -c "$(basename "$DEV")${P}[0-9]" || true)"
[ "${NPARTS:-0}" -ge 3 ] && ok "GPT has $NPARTS partitions (BIOS-boot + ESP + root)" \
    || bad "expected >=3 partitions, found ${NPARTS:-0}"

ESP="${DEV}${P}2"; ROOTP="${DEV}${P}3"

# ---- root filesystem -----------------------------------------------------------
log "mounting root ($ROOTP)"
mount -o ro "$ROOTP" "$ROOTMNT" 2>/dev/null || die "could not mount root partition $ROOTP"

[ -f "$ROOTMNT/etc/fstab" ] && grep -q "PradyOS" "$ROOTMNT/etc/fstab" \
    && ok "/etc/fstab present and PradyOS-generated" || bad "/etc/fstab missing or not PradyOS"
[ -f "$ROOTMNT/etc/default/grub" ] && grep -q 'GRUB_DISTRIBUTOR="PradyOS"' "$ROOTMNT/etc/default/grub" \
    && ok "/etc/default/grub set to PradyOS" || bad "/etc/default/grub missing PradyOS distributor"
ls "$ROOTMNT"/boot/vmlinuz-* >/dev/null 2>&1 \
    && ok "kernel present: $(basename "$(ls "$ROOTMNT"/boot/vmlinuz-* | head -1)")" || bad "no /boot/vmlinuz-*"
ls "$ROOTMNT"/boot/initrd.img-* >/dev/null 2>&1 \
    && ok "initramfs present: $(basename "$(ls "$ROOTMNT"/boot/initrd.img-* | head -1)")" || bad "no /boot/initrd.img-*"
[ -f "$ROOTMNT/boot/grub/grub.cfg" ] && grep -q "PradyOS Sovereign Edition" "$ROOTMNT/boot/grub/grub.cfg" \
    && ok "grub.cfg has the PradyOS Sovereign menuentry" || bad "grub.cfg missing or no PradyOS menuentry"
# the OS itself shipped into the rootfs (the Python package)
{ [ -d "$ROOTMNT/opt/pradyos" ] || [ -d "$ROOTMNT/usr/lib/pradyos" ] \
  || find "$ROOTMNT" -maxdepth 6 -type d -name pradyos -print -quit 2>/dev/null | grep -q . ; } \
    && ok "PradyOS payload found in rootfs" || bad "PradyOS package not found in rootfs"
[ -x "$ROOTMNT/usr/local/sbin/pradyos-install" ] \
    && ok "installer present (/usr/local/sbin/pradyos-install)" || log "  (installer not in rootfs — optional)"

# ---- EFI System Partition ------------------------------------------------------
log "mounting ESP ($ESP)"
if mount -o ro "$ESP" "$ESPMNT" 2>/dev/null; then
    { [ -f "$ESPMNT/EFI/BOOT/BOOTX64.EFI" ] || [ -d "$ESPMNT/EFI/PradyOS" ]; } \
        && ok "ESP carries a GRUB EFI bootloader" || bad "ESP has no BOOTX64.EFI / EFI/PradyOS"
else
    bad "could not mount ESP $ESP"
fi

# ---- verdict -------------------------------------------------------------------
if [ "$FAILED" = 0 ]; then
    echo -e "${c_ok}[inspect] PASS${c_z} — installed disk looks bootable and PradyOS-complete."
    echo "PRADYOS-INSPECT: PASS"
else
    die "one or more install artefacts are missing (see ✗ above)"
fi
