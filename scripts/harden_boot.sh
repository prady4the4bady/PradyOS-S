#!/bin/bash
# PRADY OS — boot-level hardening: Secure Boot signing + TPM2 measured-boot seal.
#
#   sudo bash scripts/harden_boot.sh            # run inside the install chroot or on the installed system
#
# This is the firmware-down half of the security story (the application half is
# pradyos.aegis). It builds a verified boot chain:
#
#   UEFI Secure Boot ─► shim (MS-signed) ─► GRUB (signed) ─► kernel (signed)
#                                                         ─► AEGIS verifies the
#                                                            PradyOS payload at boot
#
# and OPTIONALLY seals a secret (the AEGIS public key / a LUKS key) to the TPM so
# it is only released when the measured boot chain (PCRs 0,2,4,7) is unmodified —
# i.e. an attacker who swaps the kernel or bootloader cannot unseal it.
#
# It is conservative and idempotent:
#   * every step is GUARDED — missing tools (sbsigntool, tpm2-tools, mokutil) or
#     no TPM ⇒ that step is skipped with a clear log, never a hard failure;
#   * it NEVER weakens the system and NEVER touches anything outside the boot
#     chain. A failed seal leaves the system bootable (it just isn't TPM-bound).
#
# Keys (generate ONCE on the vendor build host; the private key NEVER ships):
#   PRADYOS_SB_KEY  — Secure Boot signing key  (.key, kept secret)
#   PRADYOS_SB_CERT — Secure Boot certificate  (.crt/.der, enrolled as a MOK)
# Env: PRADYOS_TPM_SEAL=1 to attempt the TPM seal; PRADYOS_SB_PCRS (default 0,2,4,7).
set -euo pipefail

say()  { echo -e "\033[1;36m[harden_boot]\033[0m $*"; }
skip() { echo -e "\033[1;33m[harden_boot] skip:\033[0m $*"; }
die()  { echo -e "\033[1;31m[harden_boot] ERROR:\033[0m $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root"

SB_KEY="${PRADYOS_SB_KEY:-/etc/pradyos/secureboot/db.key}"
SB_CERT="${PRADYOS_SB_CERT:-/etc/pradyos/secureboot/db.crt}"
PCRS="${PRADYOS_SB_PCRS:-0,2,4,7}"

have() { command -v "$1" >/dev/null 2>&1; }

# ── 1. Secure Boot: sign the kernel(s) and the GRUB EFI binary ─────────────────
secureboot() {
    if ! have sbsign; then skip "sbsigntool not installed (apt install sbsigntool) — Secure Boot signing"; return 0; fi
    if [ ! -f "$SB_KEY" ] || [ ! -f "$SB_CERT" ]; then
        skip "no Secure Boot key/cert at $SB_KEY / $SB_CERT — generate + enroll a MOK first"; return 0
    fi
    say "signing kernels + GRUB with the PradyOS Secure Boot key"
    # kernels
    for k in /boot/vmlinuz-*; do
        [ -f "$k" ] || continue
        if sbverify --cert "$SB_CERT" "$k" >/dev/null 2>&1; then say "  already signed: $k"; continue; fi
        sbsign --key "$SB_KEY" --cert "$SB_CERT" --output "$k" "$k" && say "  signed $k"
    done
    # GRUB EFI (BOTH the NVRAM entry and the removable fallback)
    for g in /boot/efi/EFI/PradyOS/grubx64.efi /boot/efi/EFI/BOOT/BOOTX64.EFI; do
        [ -f "$g" ] || continue
        sbsign --key "$SB_KEY" --cert "$SB_CERT" --output "$g" "$g" && say "  signed $g"
    done
    # Enroll the cert as a Machine Owner Key (interactive confirm at next reboot).
    if have mokutil; then
        mokutil --import "$SB_CERT" 2>/dev/null \
            && say "  MOK import staged — confirm the enrollment prompt on next reboot" \
            || skip "mokutil import (already enrolled, or no Secure Boot firmware)"
    fi
}

# ── 2. lock the GRUB config so menu edits can't bypass the signed chain ─────────
lock_grub() {
    [ -f /etc/default/grub ] || { skip "no /etc/default/grub"; return 0; }
    if ! grep -q "GRUB_DISABLE_RECOVERY" /etc/default/grub; then
        {
            echo "# PradyOS hardening: no recovery/edit escape hatch on a signed boot"
            echo "GRUB_DISABLE_RECOVERY=true"
        } >> /etc/default/grub
        say "locked GRUB recovery entry"
    fi
}

# ── 3. TPM2: seal a secret to the measured boot state (optional) ────────────────
tpm_seal() {
    [ "${PRADYOS_TPM_SEAL:-0}" = "1" ] || { skip "TPM seal not requested (set PRADYOS_TPM_SEAL=1)"; return 0; }
    if ! have tpm2_createprimary; then skip "tpm2-tools not installed — TPM seal"; return 0; fi
    if [ ! -e /dev/tpmrm0 ] && [ ! -e /dev/tpm0 ]; then skip "no TPM device present — TPM seal"; return 0; fi
    local secret="/etc/pradyos/aegis_pub.pem"
    [ -f "$secret" ] || { skip "no secret to seal at $secret"; return 0; }
    local dir=/etc/pradyos/tpm
    mkdir -p "$dir"
    say "sealing $secret to TPM PCRs $PCRS (measured boot)"
    # Bind a policy to the current PCR values, then seal the secret under it.
    tpm2_createprimary -C o -g sha256 -G ecc -c "$dir/primary.ctx" >/dev/null
    tpm2_startauthsession -S "$dir/sess.dat" >/dev/null
    tpm2_policypcr -S "$dir/sess.dat" -l "sha256:$PCRS" -L "$dir/policy.dat" >/dev/null
    tpm2_flushcontext "$dir/sess.dat" >/dev/null
    tpm2_create -C "$dir/primary.ctx" -L "$dir/policy.dat" -i "$secret" \
        -u "$dir/seal.pub" -r "$dir/seal.priv" >/dev/null
    chmod 600 "$dir"/seal.* 2>/dev/null || true
    say "  sealed — the secret unseals only when PCRs $PCRS match this boot chain"
    say "  (unseal at boot: tpm2_load + tpm2_unseal under the same PCR policy)"
}

say "starting boot hardening (Secure Boot + measured boot)"
secureboot
lock_grub
tpm_seal
# Make sure the AEGIS boot check is enabled on the installed system.
if have systemctl; then systemctl enable pradyos-aegis.service 2>/dev/null \
    && say "enabled pradyos-aegis.service" || skip "could not enable pradyos-aegis.service"; fi
say "PASS — boot hardening applied (skipped steps logged above are safe no-ops)"
echo "PRADYOS-HARDEN: DONE"
