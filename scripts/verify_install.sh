#!/bin/bash
# PRADY OS — automated DISK-INSTALL test (host side).
#
#   bash scripts/verify_install.sh
#
# Proves PradyOS installs to a disk and boots from it like a normal OS:
#   1. builds an ISO whose default boot entry auto-installs to /dev/vda
#   2. boots it in QEMU with a BLANK virtual disk → the guest installs itself
#      (pradyos-install) and powers off; we confirm "PRADYOS-INSTALL: DONE"
#   3. boots QEMU from that DISK only (no ISO) → confirms the installed system
#      boots and reaches "PRADYOS-SELFTEST: PASS"
#
# Tunables (env): PRADYOS_VM_MEM (3072), PRADYOS_VM_SMP (4),
#                 PRADYOS_INSTALL_TIMEOUT (1200), PRADYOS_BOOT_TIMEOUT (1800),
#                 PRADYOS_VERIFY_DIR (mktemp), PRADYOS_DISK_GB (8).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MEM="${PRADYOS_VM_MEM:-3072}"
SMP="${PRADYOS_VM_SMP:-4}"
INSTALL_TIMEOUT="${PRADYOS_INSTALL_TIMEOUT:-1200}"
BOOT_TIMEOUT="${PRADYOS_BOOT_TIMEOUT:-1800}"
DISK_GB="${PRADYOS_DISK_GB:-8}"
WORKDIR="${PRADYOS_VERIFY_DIR:-$(mktemp -d /tmp/pradyos-install.XXXXXX)}"
DISK="$WORKDIR/disk.qcow2"
ISO="$WORKDIR/pradyos-autoinstall.iso"
INSTALL_LOG="$WORKDIR/install-serial.log"
BOOT_LOG="$WORKDIR/disk-serial.log"

log() { echo -e "\033[1;36m[verify_install]\033[0m $*"; }
die() { echo -e "\033[1;31m[verify_install] FAIL:\033[0m $*" >&2
        echo "---- last 60 serial lines ----" >&2
        tail -60 "$INSTALL_LOG" "$BOOT_LOG" 2>/dev/null >&2 || true
        exit 1; }

command -v qemu-system-x86_64 >/dev/null || die "qemu-system-x86_64 not installed"
command -v qemu-img >/dev/null || die "qemu-img not installed"
mkdir -p "$WORKDIR"

QPID=""
cleanup() { [ -n "$QPID" ] && kill "$QPID" 2>/dev/null && wait "$QPID" 2>/dev/null || true; }
trap cleanup EXIT

# --- build an auto-installing ISO (default entry installs to /dev/vda) ---------
log "building auto-install ISO (this reuses the cached rootfs)…"
PRADYOS_AUTOINSTALL_TARGET=/dev/vda \
PRADYOS_ISO_NAME="$(basename "$ISO")" \
PRADYOS_BUILD_DIR="${PRADYOS_BUILD_DIR:-/root/pradyos-build}" \
    bash "$SCRIPT_DIR/build_iso.sh" >/dev/null
BUILT="$ROOT/dist/$(basename "$ISO")"
[ -f "$BUILT" ] || die "auto-install ISO not produced at $BUILT"
cp "$BUILT" "$ISO"

# --- phase 1: install to a blank disk -----------------------------------------
log "creating blank ${DISK_GB}G disk and running the guest installer…"
qemu-img create -f qcow2 "$DISK" "${DISK_GB}G" >/dev/null
: > "$INSTALL_LOG"
qemu-system-x86_64 \
    -name pradyos-install -machine q35,accel=kvm:tcg -cpu max \
    -m "$MEM" -smp "$SMP" -display none -no-reboot \
    -serial "file:$INSTALL_LOG" -monitor none \
    -drive "file=$DISK,format=qcow2,if=virtio" \
    -cdrom "$ISO" -boot d &
QPID=$!
elapsed=0
while kill -0 "$QPID" 2>/dev/null; do
    grep -aq "PRADYOS-INSTALL: FAIL" "$INSTALL_LOG" && die "guest installer reported FAIL"
    [ "$elapsed" -lt "$INSTALL_TIMEOUT" ] || die "install timed out after ${INSTALL_TIMEOUT}s"
    sleep 5; elapsed=$((elapsed + 5))
done
QPID=""
grep -aq "PRADYOS-INSTALL: DONE" "$INSTALL_LOG" || die "installer did not finish (no DONE marker)"
log "gate 1 OK: guest installed PradyOS to the disk and powered off (~${elapsed}s)"

# --- phase 2: boot from the installed disk (no ISO) ---------------------------
log "booting from the installed disk (no ISO attached)…"
: > "$BOOT_LOG"
qemu-system-x86_64 \
    -name pradyos-disk -machine q35,accel=kvm:tcg -cpu max \
    -m "$MEM" -smp "$SMP" -display none -no-reboot \
    -serial "file:$BOOT_LOG" -monitor none \
    -drive "file=$DISK,format=qcow2,if=virtio" \
    -boot c &
QPID=$!
elapsed=0
while true; do
    grep -aq "PRADYOS-SELFTEST: FAIL" "$BOOT_LOG" && die "installed system selftest FAILED"
    grep -aq "PRADYOS-SELFTEST: PASS" "$BOOT_LOG" && break
    kill -0 "$QPID" 2>/dev/null || die "installed disk did not boot (QEMU exited)"
    [ "$elapsed" -lt "$BOOT_TIMEOUT" ] || die "disk boot timed out after ${BOOT_TIMEOUT}s"
    sleep 5; elapsed=$((elapsed + 5))
done
log "gate 2 OK: installed disk boots and the selftest PASSES (~${elapsed}s)"
log "PASS — PradyOS installs to disk and boots from it (logs in $WORKDIR)"
