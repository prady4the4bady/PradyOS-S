#!/bin/bash
# PRADY OS — run the built ISO in QEMU for interactive use.
#
#   bash scripts/run_vm.sh [path/to/iso] [--gui]
#
# Default is console mode (serial on this terminal — works everywhere,
# including WSL; Ctrl-A X quits, Ctrl-A C toggles the QEMU monitor).
# --gui opens a graphical window (needs a display; WSLg counts).
#
# The Sovereign Web dashboard is forwarded to the host:
#   http://localhost:${PRADYOS_VM_PORT:-8000}/
#
# Tunables: PRADYOS_VM_PORT (8000), PRADYOS_VM_MEM (4096), PRADYOS_VM_SMP (4)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ISO="$ROOT/dist/pradyos-sovereign.iso"
GUI=0
for arg in "$@"; do
    case "$arg" in
        --gui) GUI=1 ;;
        *)     ISO="$arg" ;;
    esac
done

PORT="${PRADYOS_VM_PORT:-8000}"
MEM="${PRADYOS_VM_MEM:-4096}"
SMP="${PRADYOS_VM_SMP:-4}"

# Validate tunables up front — bad values otherwise fail deep inside QEMU with
# an opaque error.
[ "$PORT" -ge 1 ] 2>/dev/null && [ "$PORT" -le 65535 ] 2>/dev/null \
    || { echo "PRADYOS_VM_PORT must be 1-65535 (got: $PORT)" >&2; exit 2; }
[ "$MEM" -gt 0 ] 2>/dev/null \
    || { echo "PRADYOS_VM_MEM must be a positive integer MiB (got: $MEM)" >&2; exit 2; }
[ "$SMP" -gt 0 ] 2>/dev/null \
    || { echo "PRADYOS_VM_SMP must be a positive integer (got: $SMP)" >&2; exit 2; }

[ -f "$ISO" ] || { echo "ISO not found: $ISO — build it first: sudo bash scripts/build_iso.sh" >&2; exit 1; }
command -v qemu-system-x86_64 >/dev/null || { echo "qemu-system-x86_64 not installed" >&2; exit 1; }

DISPLAY_ARGS=(-display none -serial mon:stdio)
if [ "$GUI" -eq 1 ]; then
    DISPLAY_ARGS=(-display gtk -serial mon:stdio)
fi

echo "PradyOS VM starting — web dashboard: http://localhost:$PORT/  (Ctrl-A X to quit)"
exec qemu-system-x86_64 \
    -name pradyos \
    -machine q35,accel=kvm:tcg \
    -cpu max \
    -m "$MEM" -smp "$SMP" \
    "${DISPLAY_ARGS[@]}" \
    -netdev "user,id=net0,hostfwd=tcp:127.0.0.1:$PORT-:8000" \
    -device virtio-net-pci,netdev=net0 \
    -cdrom "$ISO" -boot d
