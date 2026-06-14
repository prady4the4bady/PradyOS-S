# PradyOS — Boot-level Hardening

The firmware-down half of the PradyOS security story. The application half
(runtime self-verification, tamper-evident self-disable) is [`pradyos.aegis`];
this document covers the boot chain that protects everything *below* it.

> **Stance, unchanged.** Every layer here is **tamper-EVIDENT, never
> tamper-punishing**. A failed check reports, records, and degrades PradyOS
> itself (drops to the free tier / refuses to start a service). Nothing here ever
> harms the inspecting machine — retaliatory "lock the analyst's computer"
> behaviour is explicitly out of scope and is actively blocked by the L4 critic.

## The verified boot chain

```
UEFI Secure Boot ─► shim (MS-signed) ─► GRUB (signed) ─► kernel (signed)
                                                      ─► initramfs
                                                      ─► AEGIS verifies the
                                                         PradyOS payload (*.py)
```

Each link only hands off to the next if its signature checks out, and AEGIS
extends that chain of trust up into the application payload — so a swapped
kernel, an edited bootloader, or a modified PradyOS file is all detectable.

## Components

| Piece | Where | What it does |
|-------|-------|--------------|
| `scripts/harden_boot.sh` | ISO build / installed system | signs kernel + GRUB (`sbsign`), enrolls a MOK (`mokutil`), locks GRUB recovery, optionally seals a secret to the TPM (PCRs 0,2,4,7) |
| `deploy/systemd/pradyos-aegis.service` | installed system | runs the AEGIS integrity check early in boot |
| `python -m pradyos.aegis verify` | runtime | recomputes file hashes vs the signed manifest; writes a result marker; exit 1 on tamper |
| `scripts/build_manifest.py` | vendor build host | builds + signs the integrity manifest (Ed25519) |

## One-time vendor setup

```bash
# 1. Integrity manifest signing key (private key NEVER ships)
python -c "from pradyos.licensing.vault import generate_keypair; \
           p,q=generate_keypair(); open('aegis_priv.pem','w').write(p); open('aegis_pub.pem','w').write(q)"

# 2. Secure Boot signing key + cert (enrolled as a Machine Owner Key)
openssl req -new -x509 -newkey rsa:2048 -nodes -days 3650 \
        -subj "/CN=PradyOS Secure Boot/" -keyout db.key -out db.crt
```

## At release / install time

```bash
# sign the PradyOS payload
python scripts/build_manifest.py aegis_priv.pem /etc/pradyos/integrity.manifest
cp aegis_pub.pem /etc/pradyos/aegis_pub.pem

# sign the boot chain + (optionally) seal to TPM, then enable the boot check
sudo PRADYOS_SB_KEY=db.key PRADYOS_SB_CERT=db.crt PRADYOS_TPM_SEAL=1 \
     bash scripts/harden_boot.sh
sudo cp deploy/systemd/pradyos-aegis.service /etc/systemd/system/
sudo systemctl enable pradyos-aegis.service
```

## What is testable here vs. what needs hardware

- **Unit-tested in CI**: the AEGIS manifest sign/verify, the integrity diff
  (`tests/test_aegis.py`), and the boot CLI (`tests/test_aegis_cli.py`).
- **Requires a real build host / firmware / TPM** (so it ships as guarded,
  documented shell, exercised in the ISO pipeline): `sbsign` signing, MOK
  enrollment, and TPM2 sealing. `harden_boot.sh` skips each of these with a clear
  log when the tool or device is absent, so it is always safe to run.

## Threat model (what this stops)

- **Offline tampering** — editing PradyOS files, the kernel, or GRUB on disk:
  caught by AEGIS (payload) and Secure Boot (kernel/bootloader).
- **Boot-chain substitution** — booting a different/unsigned kernel: refused by
  Secure Boot; a TPM-sealed secret won't release for the wrong PCRs.
- **License/binary forgery** — caught by the Ed25519 signatures (licenses + manifest).

It does **not** claim to stop a determined attacker with physical access and
unlimited time — no software can. It raises the cost and makes tampering
*evident*, which is the honest, achievable goal.
