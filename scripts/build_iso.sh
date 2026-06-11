#!/bin/bash
# PRADY OS — Sovereign Edition bootable-ISO builder.
#
# One command, no interaction:  sudo bash scripts/build_iso.sh
# (On Windows use scripts/build_iso.ps1, which runs this inside WSL.)
#
# Pipeline:
#   [1/7] host toolchain check (auto-installs missing Debian packages)
#   [2/7] source sync onto a native filesystem work dir
#   [3/7] base Debian rootfs via debootstrap (cached as a tarball)
#   [4/7] chroot customization (scripts/iso_chroot_setup.sh)
#   [5/7] squashfs of the rootfs
#   [6/7] hybrid BIOS+UEFI ISO via grub-mkrescue
#   [7/7] publish dist/pradyos-sovereign.iso + sha256
#
# Tunables (env):
#   PRADYOS_BUILD_DIR  work dir on a NATIVE fs (default /root/pradyos-build —
#                      do not point at /mnt/c, 9p I/O makes the build crawl)
#   PRADYOS_SUITE      Debian suite (default bookworm)
#   PRADYOS_MIRROR     Debian mirror (default http://deb.debian.org/debian)
#   PRADYOS_ISO_NAME   output name (default pradyos-sovereign.iso)
set -euo pipefail

SUITE="${PRADYOS_SUITE:-bookworm}"
MIRROR="${PRADYOS_MIRROR:-http://deb.debian.org/debian}"
WORK="${PRADYOS_BUILD_DIR:-/root/pradyos-build}"
ISO_NAME="${PRADYOS_ISO_NAME:-pradyos-sovereign.iso}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$SCRIPT_DIR/.." && pwd)"

CHROOT="$WORK/chroot"
STAGING="$WORK/iso"
CACHE="$WORK/cache"
BASE_TAR="$CACHE/rootfs-$SUITE.tar"

log()  { echo -e "\033[1;36m[build_iso]\033[0m $*"; }
die()  { echo -e "\033[1;31m[build_iso] FATAL:\033[0m $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root (debootstrap/chroot). Try: sudo bash $0"

# ---------------------------------------------------------------------------
# [1/7] Host toolchain — install anything missing, non-interactively.
# ---------------------------------------------------------------------------
log "[1/7] checking host toolchain"
NEED_PKGS=()
need() { command -v "$1" >/dev/null 2>&1 || NEED_PKGS+=("$2"); }
need debootstrap debootstrap
need mksquashfs squashfs-tools
need grub-mkrescue grub-common
need xorriso xorriso
need mformat mtools
need rsync rsync
# grub-mkrescue needs BOTH grub targets for a hybrid BIOS+UEFI image.
dpkg -s grub-pc-bin >/dev/null 2>&1 || NEED_PKGS+=(grub-pc-bin)
dpkg -s grub-efi-amd64-bin >/dev/null 2>&1 || NEED_PKGS+=(grub-efi-amd64-bin)
if [ "${#NEED_PKGS[@]}" -gt 0 ]; then
    log "installing: ${NEED_PKGS[*]}"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends "${NEED_PKGS[@]}"
fi

# ---------------------------------------------------------------------------
# [2/7] Sync source to the native-fs work dir (the repo may live on /mnt/c).
# ---------------------------------------------------------------------------
log "[2/7] syncing source: $SRC -> $WORK/src"
mkdir -p "$WORK/src" "$CACHE" "$STAGING"
rsync -a --delete \
    --exclude '.git' --exclude '.venv' --exclude 'dist' --exclude 'var' \
    --exclude '.claude' --exclude '__pycache__' --exclude '.pytest_cache' \
    --exclude '.ruff_cache' --exclude 'pytest-cache-files-*' --exclude '*.log' \
    "$SRC/" "$WORK/src/"
# Defensive: CRLF-checked-out scripts/units break bash and systemd. The repo
# enforces eol=lf via .gitattributes, but a stray checkout must not poison the image.
find "$WORK/src/scripts" "$WORK/src/deploy" -type f \( -name '*.sh' -o -name '*.service' \) \
    -exec sed -i 's/\r$//' {} +

# ---------------------------------------------------------------------------
# [3/7] Base rootfs — debootstrap once, then reuse the cached tarball.
# ---------------------------------------------------------------------------
# Unmount helper — chroot binds must never leak (a stale /dev bind makes
# rm -rf eat the host's /dev).
CHROOT_MOUNTED=0
PIP_CACHE_MOUNTED=0
unmount_chroot() {
    # Unmount the pip-cache bind FIRST: if it leaks, the next run's
    # `rm -rf "$CHROOT"` would recurse into the host's $CACHE/pip and wipe it.
    if [ "$PIP_CACHE_MOUNTED" -eq 1 ]; then
        umount -lf "$CHROOT/root/.cache" 2>/dev/null || true
        PIP_CACHE_MOUNTED=0
    fi
    [ "$CHROOT_MOUNTED" -eq 1 ] || return 0
    for m in /run /dev/pts /dev /sys /proc; do
        umount -lf "$CHROOT$m" 2>/dev/null || true
    done
    CHROOT_MOUNTED=0
}
trap unmount_chroot EXIT

if [ -f "$BASE_TAR" ]; then
    log "[3/7] reusing cached base rootfs: $BASE_TAR"
    rm -rf "$CHROOT"
    mkdir -p "$CHROOT"
    tar -xf "$BASE_TAR" -C "$CHROOT"
else
    log "[3/7] debootstrap $SUITE (first run — this downloads ~250 MB)"
    rm -rf "$CHROOT"
    debootstrap --arch=amd64 "$SUITE" "$CHROOT" "$MIRROR"
    log "caching base rootfs -> $BASE_TAR"
    tar -cf "$BASE_TAR.tmp" -C "$CHROOT" .
    mv "$BASE_TAR.tmp" "$BASE_TAR"
fi

# ---------------------------------------------------------------------------
# [4/7] Customize inside the chroot.
# ---------------------------------------------------------------------------
log "[4/7] chroot customization"
mount -t proc proc "$CHROOT/proc"
mount -t sysfs sys "$CHROOT/sys"
mount --bind /dev "$CHROOT/dev"
mount --bind /dev/pts "$CHROOT/dev/pts"
CHROOT_MOUNTED=1

# Working DNS inside the chroot + apt must not start daemons in the chroot.
cp -L /etc/resolv.conf "$CHROOT/etc/resolv.conf"
printf '#!/bin/sh\nexit 101\n' > "$CHROOT/usr/sbin/policy-rc.d"
chmod +x "$CHROOT/usr/sbin/policy-rc.d"

# Stage inputs for the chroot step.
rm -rf "$CHROOT/tmp/pradyos-iso" "$CHROOT/opt/pradyos/src"
mkdir -p "$CHROOT/tmp/pradyos-iso" "$CHROOT/opt/pradyos"
cp "$WORK/src/scripts/iso_chroot_setup.sh" "$WORK/src/scripts/vm_selftest.sh" "$CHROOT/tmp/pradyos-iso/"
cp -a "$WORK/src" "$CHROOT/opt/pradyos/src"

# Persistent pip cache across rebuilds. Track the bind so the EXIT trap can
# unmount it even if the chroot step fails under set -e.
mkdir -p "$CACHE/pip" "$CHROOT/root/.cache"
if mount --bind "$CACHE/pip" "$CHROOT/root/.cache" 2>/dev/null; then
    PIP_CACHE_MOUNTED=1
fi

# PRADYOS_LAB_IMAGE (default 1) is passed through to the chroot script.
chroot "$CHROOT" /usr/bin/env "PRADYOS_LAB_IMAGE=${PRADYOS_LAB_IMAGE:-1}" \
    /bin/bash /tmp/pradyos-iso/iso_chroot_setup.sh

if [ "$PIP_CACHE_MOUNTED" -eq 1 ]; then
    umount -lf "$CHROOT/root/.cache" 2>/dev/null || true
    PIP_CACHE_MOUNTED=0
fi
rm -f "$CHROOT/usr/sbin/policy-rc.d"
rm -rf "$CHROOT/tmp/pradyos-iso"
unmount_chroot

# ---------------------------------------------------------------------------
# [5/7] Kernel/initrd out, then squash the rootfs.
# ---------------------------------------------------------------------------
log "[5/7] building squashfs"
mkdir -p "$STAGING/live" "$STAGING/boot/grub"
VMLINUZ="$(ls -1 "$CHROOT"/boot/vmlinuz-* | sort -V | tail -1)"
INITRD="$(ls -1 "$CHROOT"/boot/initrd.img-* | sort -V | tail -1)"
[ -n "$VMLINUZ" ] && [ -n "$INITRD" ] || die "kernel/initrd not found in chroot /boot"
cp "$VMLINUZ" "$STAGING/live/vmlinuz"
cp "$INITRD"  "$STAGING/live/initrd.img"

rm -f "$STAGING/live/filesystem.squashfs"
# /boot stays out of the squash — GRUB loads kernel+initrd from the ISO.
mksquashfs "$CHROOT" "$STAGING/live/filesystem.squashfs" \
    -comp xz -b 1M -noappend -e boot

# ---------------------------------------------------------------------------
# [6/7] GRUB hybrid ISO.
# ---------------------------------------------------------------------------
log "[6/7] grub-mkrescue"
cat > "$STAGING/boot/grub/grub.cfg" <<'GRUBCFG'
set default=0
set timeout=3
serial --unit=0 --speed=115200
terminal_input serial console
terminal_output serial console

menuentry "PradyOS Sovereign Edition (live)" {
    linux /live/vmlinuz boot=live console=tty0 console=ttyS0,115200
    initrd /live/initrd.img
}
menuentry "PradyOS Sovereign Edition (live, quiet)" {
    linux /live/vmlinuz boot=live quiet console=tty0 console=ttyS0,115200
    initrd /live/initrd.img
}
GRUBCFG

# NOTE: do NOT pass --compress=xz — it fails on Debian hosts that lack
# i386-pc/hdparm.mod. Plain grub-mkrescue produces the hybrid image fine.
rm -f "$WORK/$ISO_NAME"
grub-mkrescue -o "$WORK/$ISO_NAME" "$STAGING" >/dev/null

# ---------------------------------------------------------------------------
# [7/7] Publish.
# ---------------------------------------------------------------------------
log "[7/7] publishing to $SRC/dist/"
mkdir -p "$SRC/dist"
cp "$WORK/$ISO_NAME" "$SRC/dist/$ISO_NAME"
( cd "$SRC/dist" && sha256sum "$ISO_NAME" > "$ISO_NAME.sha256" )
SIZE="$(du -h "$SRC/dist/$ISO_NAME" | cut -f1)"
log "DONE: dist/$ISO_NAME ($SIZE)"
log "verify it boots:  bash scripts/verify_boot.sh"
log "run it:           bash scripts/run_vm.sh"
