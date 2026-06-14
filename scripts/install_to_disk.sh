#!/bin/bash
# PRADY OS — disk installer (installed in the ISO as /usr/local/sbin/pradyos-install).
#
# Turns the live system into a PERMANENT install on a target disk — the way you
# install Windows / macOS / Linux — so PradyOS persists across reboots instead of
# vanishing when the live session ends.
#
#   pradyos-install /dev/sda            # interactive (asks to confirm)
#   pradyos-install /dev/sda --yes      # non-interactive
#   PRADYOS_INSTALL_DISK=/dev/vda PRADYOS_INSTALL_YES=1 pradyos-install
#
# DESTRUCTIVE: the entire target disk is wiped. Strong guards below refuse to
# touch the live medium or a disk that is currently mounted as the running root.
#
# What it does: GPT-partition (ESP + root) → unsquashfs the pristine rootfs →
# restore the kernel + a freshly-built initramfs into /boot (the live squashfs
# ships without /boot) → write fstab by UUID → install GRUB for BOTH BIOS and
# UEFI → done. Pure shell; no network.
set -euo pipefail

say()  { echo "[pradyos-install] $*"; }
die()  { echo "[pradyos-install] ERROR: $*" >&2; echo "PRADYOS-INSTALL: FAIL $*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root"

# ---- resolve target + confirmation -------------------------------------------
TARGET=""
ASSUME_YES="${PRADYOS_INSTALL_YES:-0}"
for arg in "$@"; do
    case "$arg" in
        --yes|-y) ASSUME_YES=1 ;;
        -*) die "unknown flag $arg" ;;
        *) TARGET="$arg" ;;
    esac
done
TARGET="${TARGET:-${PRADYOS_INSTALL_DISK:-}}"
# Fall back to a target named on the kernel cmdline (pradyos.autoinstall=/dev/X).
if [ -z "$TARGET" ]; then
    for tok in $(cat /proc/cmdline); do
        case "$tok" in pradyos.autoinstall=*) TARGET="${tok#pradyos.autoinstall=}"; ASSUME_YES=1 ;; esac
    done
fi
# Interactive disk selection when no target was given and we have a console.
if [ -z "$TARGET" ] && [ -t 0 ]; then
    echo "  PradyOS installer — available disks:"
    lsblk -dno NAME,SIZE,MODEL 2>/dev/null | grep -vE '^(loop|sr|ram)' | sed 's/^/    /' || true
    read -r -p "  Install PradyOS to which disk? (e.g. sda): /dev/" pick
    [ -n "$pick" ] && TARGET="/dev/$pick"
fi
[ -n "$TARGET" ] || die "no target disk (usage: pradyos-install /dev/sdX [--yes])"
[ -b "$TARGET" ] || die "$TARGET is not a block device"

# ---- safety: never the live medium or the running root ------------------------
ROOTSRC="$(findmnt -n -o SOURCE / 2>/dev/null || true)"
case "$ROOTSRC" in "$TARGET"*) die "$TARGET hosts the running root filesystem" ;; esac
# The live medium (ISO) is mounted under /run/live; refuse its backing device.
for src in $(findmnt -rn -o SOURCE /run/live/medium 2>/dev/null || true); do
    case "$TARGET" in "${src%[0-9]}"*) die "$TARGET is the live install medium" ;; esac
done

# The squashfs FILE (not its mountpoint dir of the same name under /run/live/rootfs).
SQUASH="$(find /run/live -name 'filesystem.squashfs' -type f 2>/dev/null | head -1)"
[ -n "$SQUASH" ] || die "could not locate the live filesystem.squashfs"
MEDIUM="$(dirname "$SQUASH")"   # /run/live/medium/live — holds vmlinuz + initrd.img
KVER="$(ls -1 /lib/modules 2>/dev/null | sort -V | tail -1)"
[ -n "$KVER" ] || die "no kernel modules found (cannot determine kernel version)"

say "target disk : $TARGET   (kernel $KVER)"
if [ "$ASSUME_YES" != 1 ]; then
    echo "    THIS WILL ERASE ALL DATA ON $TARGET."
    read -r -p "    Type 'yes' to install PradyOS: " reply
    [ "$reply" = "yes" ] || die "aborted by operator"
fi

# Partition device naming: /dev/sda → sda1 ; /dev/nvme0n1 → nvme0n1p1
case "$TARGET" in *[0-9]) PSEP="p" ;; *) PSEP="" ;; esac
BIOSP="${TARGET}${PSEP}1"
ESP="${TARGET}${PSEP}2"
ROOTP="${TARGET}${PSEP}3"

# ---- partition + format -------------------------------------------------------
say "partitioning (GPT: BIOS-boot + 512M ESP + root)"
wipefs -a "$TARGET" >/dev/null 2>&1 || true
sgdisk --zap-all "$TARGET" >/dev/null
# A 1 MiB BIOS-boot partition (ef02) gives legacy-BIOS GRUB a place to embed
# core.img on a GPT disk — without it, i386-pc grub-install can't embed and the
# disk won't boot under BIOS. ESP (ef00) covers UEFI; root holds the system.
sgdisk -n1:0:+1M   -t1:ef02 -c1:"BIOS boot"    "$TARGET" >/dev/null
sgdisk -n2:0:+512M -t2:ef00 -c2:"EFI System"   "$TARGET" >/dev/null
sgdisk -n3:0:0     -t3:8300 -c3:"pradyos-root" "$TARGET" >/dev/null
partprobe "$TARGET" 2>/dev/null || true
udevadm settle 2>/dev/null || true
sleep 1

say "formatting"
mkfs.fat -F32 -n PRADYOS-ESP "$ESP" >/dev/null
mkfs.ext4 -F -L pradyos-root "$ROOTP" >/dev/null

# ---- copy the system ----------------------------------------------------------
T=/mnt/pradyos-target
mkdir -p "$T"
mount "$ROOTP" "$T"
say "copying root filesystem (unsquashfs)"
unsquashfs -f -d "$T" "$SQUASH" >/dev/null
mkdir -p "$T/boot/efi"
mount "$ESP" "$T/boot/efi"

# The rootfs carries its own /boot now; make sure the running kernel + a fresh
# initrd are present (rebuilt in the chroot below).
say "restoring kernel + initramfs"
[ -f "$T/boot/vmlinuz-$KVER" ] || cp "$MEDIUM/vmlinuz" "$T/boot/vmlinuz-$KVER"
[ -f "$T/boot/initrd.img-$KVER" ] || cp "$MEDIUM/initrd.img" "$T/boot/initrd.img-$KVER"

# ---- fstab --------------------------------------------------------------------
ROOT_UUID="$(blkid -s UUID -o value "$ROOTP")"
ESP_UUID="$(blkid -s UUID -o value "$ESP")"
cat > "$T/etc/fstab" <<EOF
# PradyOS — generated by pradyos-install
UUID=$ROOT_UUID  /          ext4  errors=remount-ro  0 1
UUID=$ESP_UUID   /boot/efi  vfat  umask=0077         0 2
EOF

# A normal (non-live) boot needs a default GRUB config.
cat > "$T/etc/default/grub" <<'EOF'
GRUB_DEFAULT=0
GRUB_TIMEOUT=3
GRUB_DISTRIBUTOR="PradyOS"
GRUB_CMDLINE_LINUX_DEFAULT=""
GRUB_CMDLINE_LINUX="console=tty0 console=ttyS0,115200"
GRUB_TERMINAL="console serial"
GRUB_SERIAL_COMMAND="serial --unit=0 --speed=115200"
EOF

# ---- install GRUB in the new system ------------------------------------------
say "installing bootloader (BIOS + UEFI)"
for d in dev proc sys run; do mount --bind "/$d" "$T/$d"; done
[ -d /sys/firmware/efi/efivars ] && mount --bind /sys/firmware/efi/efivars "$T/sys/firmware/efi/efivars" 2>/dev/null || true

chroot "$T" /bin/bash <<CHROOT
export DEBIAN_FRONTEND=noninteractive
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# Rebuild the initramfs for a normal disk boot (the live initrd is inert without
# boot=live; a freshly-built one is the safe, supported path).
echo "[install] update-initramfs:"
update-initramfs -u -k "$KVER" 2>&1 | tail -3 || update-initramfs -c -k "$KVER" 2>&1 | tail -3 || true
# BIOS (legacy): embeds core.img in the ef02 BIOS-boot partition on this GPT disk.
echo "[install] grub-install BIOS:"
if grub-install --target=i386-pc --recheck --boot-directory=/boot "$TARGET" 2>&1; then
    echo "PRADYOS-INSTALL: grub-bios OK"
else
    echo "PRADYOS-INSTALL: grub-bios FAILED"
fi
# UEFI: NVRAM entry + a removable fallback so firmware that ignores NVRAM boots us.
if [ -d /sys/firmware/efi ]; then
    grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=PradyOS --recheck 2>&1 || true
    grub-install --target=x86_64-efi --efi-directory=/boot/efi --removable 2>&1 || true
fi
update-grub 2>&1 | tail -3 || grub-mkconfig -o /boot/grub/grub.cfg 2>&1 | tail -3 || true
CHROOT

# Guarantee a self-contained, serial-enabled grub.cfg — update-grub can mis-probe
# devices inside a synthetic chroot, so we write a known-good config by UUID.
mkdir -p "$T/boot/grub"
cat > "$T/boot/grub/grub.cfg" <<EOF
set timeout=3
set default=0
serial --unit=0 --speed=115200
terminal_input serial console
terminal_output serial console
insmod part_gpt
insmod ext2
menuentry "PradyOS Sovereign Edition" {
    search --no-floppy --fs-uuid --set=root $ROOT_UUID
    linux /boot/vmlinuz-$KVER root=UUID=$ROOT_UUID ro console=tty0 console=ttyS0,115200
    initrd /boot/initrd.img-$KVER
}
EOF

# ---- done ---------------------------------------------------------------------
sync
umount -R "$T" 2>/dev/null || true
say "installed PradyOS to $TARGET"
echo "PRADYOS-INSTALL: DONE $TARGET"
