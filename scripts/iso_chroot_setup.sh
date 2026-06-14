#!/bin/bash
# PRADY OS — runs INSIDE the image chroot (invoked by build_iso.sh).
# Installs the OS payload: kernel + live-boot, redis, the pradyos package in
# a venv, systemd units for every plane, networking, autologin consoles, and
# the first-boot integration selftest.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Hardened by default (safe-by-default): root is locked and there is no console
# autologin. Build with PRADYOS_LAB_IMAGE=1 for a lab image (known root password
# 'pradyos' + root autologin on tty1/ttyS0) so a developer can poke at the VM.
# The boot selftest is unaffected either way — it runs as a systemd unit and
# probes 127.0.0.1, and verify_boot's serial-login check is warn-only.
LAB_IMAGE="${PRADYOS_LAB_IMAGE:-0}"

# Stash the working resolver that build_iso.sh placed here: installing
# systemd-resolved (below) replaces /etc/resolv.conf with a symlink to a stub
# (/run/systemd/resolve/stub-resolv.conf) that nothing serves inside this build
# chroot, which breaks DNS for the later `pip install`. We restore it before pip.
cp -L /etc/resolv.conf /tmp/resolv.conf.build 2>/dev/null || true

echo "[chroot] installing system packages"
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    linux-image-amd64 live-boot systemd-sysv systemd-resolved \
    dbus udev kmod \
    redis-server \
    python3 python3-venv python3-pip \
    ca-certificates curl iproute2 procps less nano \
    `# disk-install toolchain: lets the live OS install itself to a hard disk.` \
    `# grub2-common provides grub-install/update-grub; the -bin pkgs the platforms.` \
    gdisk dosfstools squashfs-tools util-linux \
    grub2-common grub-pc-bin grub-efi-amd64-bin efibootmgr
# live-boot installs initramfs hooks; make sure the (already unpacked) kernel
# initrd is regenerated with them.
update-initramfs -u

echo "[chroot] identity"
echo pradyos > /etc/hostname
cat > /etc/hosts <<'HOSTS'
127.0.0.1   localhost
127.0.1.1   pradyos
::1         localhost ip6-localhost ip6-loopback
HOSTS
cat > /etc/issue <<'ISSUE'

  PRADY OS — Sovereign Edition  \n \l

ISSUE
# Console credential. Lab image: known root password; hardened: lock root.
if [ "$LAB_IMAGE" = 1 ]; then
    echo 'root:pradyos' | chpasswd
else
    passwd -l root
fi

echo "[chroot] pradyos service user + sovereign directories"
useradd --system --user-group --home-dir /var/lib/pradyos --create-home \
    --shell /usr/sbin/nologin pradyos || true
install -d -m 0775 -o pradyos -g pradyos /var/log/pradyos /var/lib/pradyos/state
install -d -m 0755 /etc/pradyos
# Shared append-only ledger: pre-create so the first writer (root TITAN or a
# pradyos plane) doesn't lock the others out with a 0644 root:root file.
touch /var/log/pradyos/audit.jsonl
chown pradyos:pradyos /var/log/pradyos/audit.jsonl
chmod 0664 /var/log/pradyos/audit.jsonl
# /run/pradyos (titan.sock home) — group-traversable for the pradyos planes.
echo 'd /run/pradyos 0775 root pradyos -' > /etc/tmpfiles.d/pradyos.conf

# Restore a working resolver for pip — systemd-resolved's postinst turned
# /etc/resolv.conf into a dangling stub symlink during the apt step above.
# (At boot the image runs systemd-resolved, which owns this file properly.)
rm -f /etc/resolv.conf
if [ -s /tmp/resolv.conf.build ]; then
    cp /tmp/resolv.conf.build /etc/resolv.conf
else
    printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' > /etc/resolv.conf
fi

echo "[chroot] python venv + pradyos package"
VENV=/opt/pradyos/.venv
python3 -m venv "$VENV"
"$VENV/bin/pip" install --no-input --upgrade pip wheel

# Runtime dependency set for the image. This mirrors pyproject's core deps but
# deliberately OMITS chromadb: chromadb pulls hnswlib, a C++ extension with no
# prebuilt wheel for this platform, which therefore tries to COMPILE — and the
# minimal image ships no toolchain, so the build dies right here. Memory Citadel
# already degrades to a documented no-op mode when chromadb is absent
# (see pradyos/memory_citadel/store.py), so the image loses nothing the boot
# selftest depends on. scikit-learn IS kept: pradyos.sovereign_web imports
# pradyos.core.anomaly_watch at module load, which imports sklearn eagerly, and
# sklearn ships a manylinux wheel (no compiler needed). redis = bus client,
# uvicorn = ASGI server for pradyos-web — both runtime-required here.
"$VENV/bin/pip" install --no-input \
    "psutil>=5.9" "rich>=13.7" "textual>=0.58" "aiohttp>=3.9" \
    "pydantic>=2.5" "orjson>=3.9" "anyio>=4.2" "click>=8.1" "httpx>=0.27" \
    "starlette>=0.27" "fastapi>=0.100" "scikit-learn>=1.3" \
    "redis>=5.0" "uvicorn>=0.30"
# Install the package itself WITHOUT re-resolving deps, so chromadb cannot sneak
# back in through pyproject. --no-deps is safe: every runtime dep is pinned above.
"$VENV/bin/pip" install --no-input --no-deps -e /opt/pradyos/src

# Fail the BUILD now (not silently at first boot) if any boot-enabled plane
# cannot import in the image's own interpreter — this catches a missing or
# ABI-broken dependency the moment it happens, with a real traceback.
echo "[chroot] verifying boot-plane imports"
"$VENV/bin/python" - <<'PYCHECK'
import importlib
import sys

PLANES = [
    "pradyos.titan_ops.daemon",
    "pradyos.warden_grid.monitor",
    "pradyos.imperium.kernel",
    "pradyos.oracle.daemon",
    "pradyos.oracle.admission_bridge",
    "pradyos.sovereign_web",
]
failures = []
for mod in PLANES:
    try:
        importlib.import_module(mod)
    except Exception as exc:  # noqa: BLE001 — surface the first import break
        failures.append(f"  {mod}: {type(exc).__name__}: {exc}")
if failures:
    sys.stderr.write("BOOT-PLANE IMPORT FAILURES:\n" + "\n".join(failures) + "\n")
    raise SystemExit(1)
print("[chroot] all boot planes import OK")
PYCHECK

echo "[chroot] systemd units"
cp /opt/pradyos/src/deploy/systemd/pradyos-*.service /etc/systemd/system/
install -m 0755 /tmp/pradyos-iso/vm_selftest.sh /usr/local/sbin/pradyos-selftest
install -m 0755 /tmp/pradyos-iso/install_to_disk.sh /usr/local/sbin/pradyos-install

# Disk-install services — both gated on the kernel cmdline so a NORMAL live boot
# never touches a disk. `pradyos.installer=interactive` (the "Install PradyOS to
# disk" boot-menu entry) runs the installer on the console; `pradyos.autoinstall=
# /dev/X` does an unattended install then powers off (used by verify_install +
# kiosk/unattended deployments).
cat > /etc/systemd/system/pradyos-installer.service <<'UNIT'
[Unit]
Description=PradyOS interactive disk installer
ConditionKernelCommandLine=pradyos.installer
After=systemd-user-sessions.service plymouth-quit-wait.service
Conflicts=getty@tty1.service

[Service]
Type=idle
ExecStart=/usr/local/sbin/pradyos-install
StandardInput=tty
StandardOutput=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/pradyos-autoinstall.service <<'UNIT'
[Unit]
Description=PradyOS unattended disk install (pradyos.autoinstall=/dev/X), then power off
ConditionKernelCommandLine=pradyos.autoinstall
After=local-fs.target systemd-udev-settle.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/pradyos-install
ExecStopPost=/bin/systemctl poweroff
StandardOutput=journal+console
StandardError=journal+console

[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/pradyos-selftest.service <<'UNIT'
[Unit]
Description=PradyOS first-boot integration selftest (emits PRADYOS-SELFTEST marker on console)
After=pradyos-web.service pradyos-imperium.service network-online.target
Wants=pradyos-web.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/pradyos-selftest
RemainAfterExit=yes
TimeoutStartSec=900

[Install]
WantedBy=multi-user.target
UNIT

systemctl enable \
    redis-server \
    pradyos-titan pradyos-warden pradyos-imperium \
    pradyos-oracle pradyos-admission pradyos-web \
    pradyos-selftest \
    pradyos-installer pradyos-autoinstall
# pradyos-throne stays disabled: interactive TUI, launched per session.

echo "[chroot] networking (DHCP on any ethernet — QEMU user-net friendly)"
cat > /etc/systemd/network/80-dhcp.network <<'NET'
[Match]
Name=en* eth*

[Network]
DHCP=yes
NET
systemctl enable systemd-networkd systemd-resolved
# Don't let an unconfigured link stall boot for the default 120 s.
mkdir -p /etc/systemd/system/systemd-networkd-wait-online.service.d
cat > /etc/systemd/system/systemd-networkd-wait-online.service.d/timeout.conf <<'CONF'
[Service]
ExecStart=
ExecStart=/lib/systemd/systemd-networkd-wait-online --any --timeout=30
CONF

if [ "$LAB_IMAGE" = 1 ]; then
    echo "[chroot] autologin consoles (lab image)"
    for getty in 'getty@tty1' 'serial-getty@ttyS0'; do
        mkdir -p "/etc/systemd/system/${getty}.service.d"
        cat > "/etc/systemd/system/${getty}.service.d/autologin.conf" <<'CONF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I $TERM
CONF
    done
else
    echo "[chroot] hardened image — no console autologin"
fi

echo "[chroot] cleanup"
# Hand /etc/resolv.conf back to systemd-resolved for the SHIPPED image. The
# build-time static file (set before pip) must not ride along, or the booted
# system would ignore DHCP-provided DNS and keep the build host's nameservers.
rm -f /etc/resolv.conf /tmp/resolv.conf.build
ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
apt-get clean
rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*.deb
# Each boot must mint its own machine identity.
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id

echo "[chroot] done"
