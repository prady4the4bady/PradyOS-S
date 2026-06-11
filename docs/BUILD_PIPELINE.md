# PradyOS — Automated OS Build Pipeline, VM Configuration & Integration Tests

This document covers the **Sovereign Edition OS image**: how the bootable ISO
is built with one command, how to run it in a virtual machine, and how the
automated integration tests verify that all core planes are built and
functioning together. (The fast Python gates — lint, pytest, `scripts/prove.py` —
are unchanged and live in `.github/workflows/ci.yml`.)

```
 repo ──► [build_iso.(ps1|sh)] ──► debootstrap ──► chroot setup ──► squashfs ──► grub-mkrescue
                                   (cached)        venv + units                  hybrid BIOS/UEFI
                                                                                      │
                                                                            dist/pradyos-sovereign.iso
                                                                                      │
            [verify_boot.sh] ◄── QEMU headless boot ◄─────────────────────────────────┘
              │        │
              │        └─ serial console ◄── in-guest pradyos-selftest.service
              └─ host HTTP probes ──► forwarded :8000 (Sovereign Web)
```

---

## 1. Building the OS image (one command, no interaction)

### Windows (this dev box)

```powershell
.\scripts\build_iso.ps1            # build dist\pradyos-sovereign.iso
.\scripts\build_iso.ps1 -Verify    # build, then run the full boot verification
.\scripts\build_iso.ps1 -VerifyOnly  # boot-test an existing ISO
```

The wrapper runs `scripts/build_iso.sh` as root inside WSL (`-Distro Debian`
by default). All heavy I/O happens on the WSL-native filesystem
(`/root/pradyos-build`); only source-in / ISO-out cross `/mnt/c`.

### Linux / WSL / CI

```bash
sudo bash scripts/build_iso.sh      # or: make iso
```

### What the builder does

| Stage | What | Notes |
|---|---|---|
| 1/7 | Toolchain check | auto-installs missing packages (debootstrap, squashfs-tools, grub-pc-bin, grub-efi-amd64-bin, xorriso, mtools, rsync) |
| 2/7 | Source sync | rsync to native fs; CRLF scrubbed from `*.sh` / `*.service` defensively |
| 3/7 | Base rootfs | `debootstrap bookworm` — **cached** as a tarball, so rebuilds skip the ~250 MB download |
| 4/7 | Chroot setup | `scripts/iso_chroot_setup.sh`: kernel + live-boot, redis-server, `/opt/pradyos/.venv` with the `pradyos` package, systemd units for every plane, DHCP networking, autologin consoles, the selftest unit. Runtime deps are pinned explicitly and the package installs `--no-deps` (see below); a build-time import gate fails the build if any boot plane can't import. pip cache persists across builds |
| 5/7 | squashfs | `mksquashfs -comp xz -b 1M`, `/boot` excluded (GRUB loads kernel/initrd from the ISO) |
| 6/7 | ISO | `grub-mkrescue` hybrid BIOS+UEFI. **Do not add `--compress=xz`** — it fails on hosts missing `i386-pc/hdparm.mod` |
| 7/7 | Publish | `dist/pradyos-sovereign.iso` + `.sha256` |

Tunables (env): `PRADYOS_BUILD_DIR`, `PRADYOS_SUITE`, `PRADYOS_MIRROR`,
`PRADYOS_ISO_NAME`.

### What's inside the image

- Debian bookworm + kernel (`linux-image-amd64`) + `live-boot` (RAM-overlay live system; GRUB serial+VGA consoles: `console=tty0 console=ttyS0,115200`).
- `redis-server` (the sovereign event bus) bound to localhost.
- The `pradyos` package in `/opt/pradyos/.venv`, source at `/opt/pradyos/src`, editable-installed `--no-deps` over an explicitly pinned runtime set (psutil, rich, textual, aiohttp, pydantic, orjson, anyio, click, httpx, starlette, fastapi, scikit-learn, redis, uvicorn). **`chromadb` is deliberately excluded** — it pulls `hnswlib`, a C++ extension with no prebuilt wheel that the toolchain-free image cannot compile; Memory Citadel already degrades to a documented no-op mode without it. A build-time import check (`importlib.import_module` over all boot planes) fails the build immediately if any pinned dep is missing or ABI-broken, instead of letting it surface as a unit crash at first boot.
- Enabled units: `redis-server`, `pradyos-titan` (root, group `pradyos` — the daemon chmods its control socket 0660), `pradyos-warden`, `pradyos-imperium`, `pradyos-oracle`, `pradyos-admission`, `pradyos-web` (uvicorn `:8000`), `pradyos-selftest`. `pradyos-throne` ships disabled (interactive TUI).
- All daemon units are `Type=exec` — the daemons do not implement sd_notify, and `Type=notify` units stall the boot transaction forever waiting for `READY=1`.
- ORACLE / Admission / Web units omit `MemoryDenyWriteExecute=` and `SystemCallFilter=` — the numpy / scikit-learn / onnxruntime stack maps W+X pages and dies under those at import time.
- Login: `root` / `pradyos`, autologin on tty1 and ttyS0 (**lab image — harden before any non-lab use**).

---

## 2. Running the OS in a virtual machine

### QEMU (scripted — recommended)

```powershell
.\scripts\run_vm.ps1                 # Windows: console-mode VM via WSL QEMU
.\scripts\run_vm.ps1 -Gui            # graphical window via WSLg
```
```bash
bash scripts/run_vm.sh [--gui]       # Linux/WSL; or: make vm
```

Both forward the Sovereign Web dashboard to **http://localhost:8000/** and use
KVM when available (`accel=kvm:tcg` falls back to software emulation —
expect a slow boot without KVM). `-cpu max` is required under TCG: the ML
wheels use AVX, which the default `qemu64` CPU model lacks. Console mode:
`Ctrl-A X` quits, `Ctrl-A C` toggles the QEMU monitor.

### VirtualBox (manual)

1. New VM → Type *Linux*, Version *Debian (64-bit)*; 3072+ MB RAM, 2+ CPUs; no virtual disk needed (live image runs from RAM).
2. Settings → Storage → attach `dist/pradyos-sovereign.iso` to the optical drive.
3. Settings → Network → Adapter 1 = NAT → Port Forwarding → add `TCP, host 127.0.0.1:8000 → guest :8000`.
4. Boot. Console autologs in as root; dashboard at `http://localhost:8000/`.

### Hyper-V (manual)

1. New → Virtual Machine → **Generation 1** (simplest), 4096 MB, Default Switch.
2. Attach the ISO to the DVD drive and boot. (Generation 2 also works — the ISO is UEFI-hybrid — but disable Secure Boot, as GRUB is unsigned.)
3. Find the guest IP via `ip addr` on the console; browse `http://<guest-ip>:8000/`.

### VMware Workstation / Fusion

Typical install → "Installer disc image" = the ISO → guest OS *Debian 12 64-bit* → NAT. Same dashboard/port story as VirtualBox.

---

## 3. Automated integration tests

Three layers, all driven from one command:

```bash
bash scripts/verify_boot.sh          # or: make verify-os
# Windows: .\scripts\build_iso.ps1 -VerifyOnly
```

**Layer 1 — in-guest selftest (`pradyos-selftest.service`).** A oneshot unit
baked into the image (source: `scripts/vm_selftest.sh`) that runs after boot:

- *Gated planes must converge:* `redis-server`, `pradyos-titan`,
  `pradyos-warden`, `pradyos-imperium`, `pradyos-web` all `active`.
- *Web plane healthy:* `/api/health`, `/api/status`, `/api/metrics` answer.
- *Cross-plane round-trip:* `POST /api/v1/polygon/build` a 4×3 rectangle, then
  assert `contains(2,1) == true` and `contains(9,9) == false` — proving the
  HTTP plane, the structure plane, and the app factory work **together**.
- *Informational:* `pradyos-oracle` / `pradyos-admission` states and the
  failed-unit count are reported but not gated (they want an LLM backend).

It emits machine-readable markers on the serial console:
`PRADYOS-SELFTEST: PASS` / `PRADYOS-SELFTEST: FAIL <reason>` (+ `…-DEBUG:`
unit states and web-journal tail on failure).

**Layer 2 — host harness (`scripts/verify_boot.sh`).** Boots the ISO headless
in QEMU with the serial console captured to a file and `:8000` forwarded;
waits for the PASS marker (fail-fast on FAIL), then **independently** probes
the API from the host through the forwarded port (health + its own polygon
round-trip), proving guest DHCP networking and the full HTTP path. A missing
login prompt is warn-only. On failure it dumps the last 60 serial lines.
Tunables: `PRADYOS_VM_PORT` (8888), `PRADYOS_VM_MEM` (3072), `PRADYOS_VM_SMP`
(4), `PRADYOS_BOOT_TIMEOUT` (1800 s — generous for TCG; KVM boots in ~1-3 min).

**Layer 3 — pytest + CI.**

- `tests/integration/test_os_image.py` wraps the harness for pytest. Opt-in
  (`PRADYOS_OS_IMAGE_TESTS=1` + a built ISO), auto-skips otherwise, and is
  intentionally **not** in `scripts/prove.py`'s module list — the 353/353
  prove gate stays pure-Python and fast.
- `.github/workflows/os-image.yml` builds the ISO and runs the boot
  verification on every push that touches image inputs (`scripts/*iso*`,
  `deploy/systemd/**`, the harness), weekly as a canary, and on demand
  (`workflow_dispatch`). The ISO and the serial log are uploaded as artifacts;
  the serial log is the primary debugging artifact on failure.

---

## 4. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `grub-mkrescue` fails mentioning `hdparm.mod` | You passed `--compress=xz`. Don't — plain `grub-mkrescue` works. |
| Boot hangs with units `activating` forever | A `Type=notify` unit without sd_notify in the daemon. All pradyos units must stay `Type=exec` until the daemons signal readiness. |
| ORACLE/Web crash at import (`SIGSYS`/`SIGSEGV`) | `SystemCallFilter=`/`MemoryDenyWriteExecute=` re-added to an ML-loading unit. Remove them (see unit comments). |
| `Missing '='` warnings from systemd at boot | A truncated/corrupted unit file made it into the image — check `deploy/systemd/*.service` end with `[Install]`. |
| Illegal instruction in guest under TCG | QEMU launched without `-cpu max` (ML wheels need AVX). |
| Build dies at `[chroot] python venv` with `Temporary failure in name resolution` | Installing `systemd-resolved` replaces `/etc/resolv.conf` with a dangling stub symlink mid-build, breaking DNS for pip. `iso_chroot_setup.sh` stashes the working resolver before apt and restores it before pip — keep that restore intact. |
| Build dies at `[chroot] python venv` compiling `hnswlib`/`chromadb` | A heavy dep with no wheel was added to the chroot's pinned install. Keep the image's runtime set wheel-only (no compiler ships in the image); leave optional native deps like `chromadb` out — `iso_chroot_setup.sh` installs the package `--no-deps`. |
| Build dies at `[chroot] verifying boot-plane imports` | A boot plane lost a runtime dep. The traceback names the module and the missing import; add the dep to the pinned list in `iso_chroot_setup.sh` (or make the import lazy). |
| Build crawls | `PRADYOS_BUILD_DIR` points at `/mnt/c`. Keep it on the WSL-native fs. |
| No `/dev/kvm` in WSL | Boot test still works via TCG, just slower. Enable nested virtualization in `.wslconfig` for speed. |
| `python scripts/prove.py` dies on `✓` when redirected (Windows) | Run with `PYTHONIOENCODING=utf-8`. |
| Guest has no network / host probes fail | The VM must provide DHCP (QEMU user-net and VirtualBox NAT do). The image runs systemd-networkd with DHCP on `en*`/`eth*`. |
