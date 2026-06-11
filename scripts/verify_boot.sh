#!/bin/bash
# PRADY OS — automated OS-image integration test (host side).
#
#   bash scripts/verify_boot.sh [path/to/pradyos-sovereign.iso]
#
# Boots the ISO headless in QEMU (KVM if available, TCG otherwise), captures
# the serial console, and grades the boot:
#
#   1. waits for the in-guest selftest marker  PRADYOS-SELFTEST: PASS
#      (the guest gates redis + titan + warden + imperium + web and runs a
#      cross-plane structure round-trip — see scripts/vm_selftest.sh)
#   2. independently probes the Sovereign Web API from the HOST through the
#      forwarded port (proves guest networking + the full HTTP path)
#   3. checks a login prompt appeared on serial (warn-only)
#
# Exit 0 = image verified. Tunables (env):
#   PRADYOS_VM_PORT      host port forwarded to guest :8000   (default 8888)
#   PRADYOS_VM_MEM       guest RAM in MiB                     (default 3072)
#   PRADYOS_VM_SMP       guest vCPUs                          (default 4)
#   PRADYOS_BOOT_TIMEOUT seconds to wait for the PASS marker  (default 1800)
#   PRADYOS_VERIFY_DIR   where serial.log lands               (default mktemp)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ISO="${1:-$ROOT/dist/pradyos-sovereign.iso}"
PORT="${PRADYOS_VM_PORT:-8888}"
MEM="${PRADYOS_VM_MEM:-3072}"
SMP="${PRADYOS_VM_SMP:-4}"
TIMEOUT="${PRADYOS_BOOT_TIMEOUT:-1800}"
WORKDIR="${PRADYOS_VERIFY_DIR:-$(mktemp -d /tmp/pradyos-verify.XXXXXX)}"
SERIAL="$WORKDIR/serial.log"
API="http://127.0.0.1:$PORT"

log()  { echo -e "\033[1;36m[verify_boot]\033[0m $*"; }
die()  { echo -e "\033[1;31m[verify_boot] FAIL:\033[0m $*" >&2
         echo "---- last 60 serial lines ($SERIAL) ----" >&2
         tail -60 "$SERIAL" 2>/dev/null >&2 || true
         exit 1; }

[ -f "$ISO" ] || die "ISO not found: $ISO (build it: sudo bash scripts/build_iso.sh)"
command -v qemu-system-x86_64 >/dev/null || die "qemu-system-x86_64 not installed"

mkdir -p "$WORKDIR"; : > "$SERIAL"
log "ISO:    $ISO"
log "serial: $SERIAL"
log "API:    $API (forwarded to guest :8000)"

QPID=""
cleanup() { [ -n "$QPID" ] && kill "$QPID" 2>/dev/null && wait "$QPID" 2>/dev/null || true; }
trap cleanup EXIT

qemu-system-x86_64 \
    -name pradyos-verify \
    -machine q35,accel=kvm:tcg \
    -cpu max \
    -m "$MEM" -smp "$SMP" \
    -display none -no-reboot \
    -serial "file:$SERIAL" -monitor none \
    -netdev "user,id=net0,hostfwd=tcp:127.0.0.1:$PORT-:8000" \
    -device virtio-net-pci,netdev=net0 \
    -cdrom "$ISO" -boot d &
QPID=$!
log "QEMU pid $QPID — waiting up to ${TIMEOUT}s for the in-guest selftest"

# --- Gate 1: in-guest selftest marker over serial ----------------------------
elapsed=0
while true; do
    grep -aq "PRADYOS-SELFTEST: FAIL" "$SERIAL" && die "in-guest selftest FAILED"
    grep -aq "PRADYOS-SELFTEST: PASS" "$SERIAL" && break
    kill -0 "$QPID" 2>/dev/null || die "QEMU exited before selftest completed"
    [ "$elapsed" -lt "$TIMEOUT" ] || die "timeout: no PRADYOS-SELFTEST marker after ${TIMEOUT}s"
    sleep 5; elapsed=$((elapsed + 5))
done
log "gate 1 OK: in-guest selftest PASS (after ~${elapsed}s)"

# --- Gate 2: host-side probes through the forwarded port ---------------------
curl -fsS --max-time 20 "$API/api/health" | grep -aq '"status"' \
    || die "host probe: /api/health unreachable or malformed via $API"
curl -fsS --max-time 20 -X POST "$API/api/v1/polygon/build" \
    -H 'Content-Type: application/json' \
    -d '{"vertices": [[0,0],[10,0],[10,10],[0,10]]}' >/dev/null \
    || die "host probe: polygon build failed via $API"
curl -fsS --max-time 20 "$API/api/v1/polygon/contains?x=5&y=5" | grep -aq '"contains":true' \
    || die "host probe: polygon containment wrong via $API"
log "gate 2 OK: host-side API probes pass (network + HTTP path verified)"

# --- Gate 3 (warn-only): login prompt on serial -------------------------------
if grep -aqE "(pradyos login:|automatically logged in)" "$SERIAL"; then
    log "gate 3 OK: console login reached"
else
    log "gate 3 WARN: no login prompt seen on serial yet (selftest+API already passed)"
fi

# Surface the informational plane states recorded by the guest.
grep -a "PRADYOS-SELFTEST: info" "$SERIAL" | sed 's/^/[verify_boot] guest /' || true

log "PASS — image verified (serial log kept at $SERIAL)"
