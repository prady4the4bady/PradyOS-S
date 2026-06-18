# PradyOS — AppArmor profiles (privileged-lane hardening) — STUBS

Mandatory-access-control confinement for the PradyOS daemons, so a compromised
process can only touch what its plane legitimately needs. This complements the
existing defence-in-depth: the systemd sandboxing directives already on each unit
(`NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`, …), the AEGIS integrity
check, and the boot-level chain. AppArmor adds kernel-enforced MAC on top.

> **These are STUBS.** They deny the dangerous defaults out of the box, but the
> command/file allowlists (especially TITAN's) are intentionally broad so nothing
> breaks on first enrollment. Tighten them in *complain* mode (below) before
> flipping to *enforce* in production.

## Profiles

| File | Confines | Attach to |
|------|----------|-----------|
| `pradyos-titan` | TITAN OPS — the privileged command runner (with a child profile for spawned commands) | `pradyos-titan.service` |
| `pradyos-imperium` | IMPERIUM orchestration kernel (no exec, no setuid) | `pradyos-imperium.service` |
| `pradyos-service` | shared baseline: WARDEN, ORACLE, AURORA THRONE, Sovereign Web | the other `pradyos-*.service` units |

## Enroll

```bash
# 1. install the profiles
sudo cp deploy/apparmor/pradyos-* /etc/apparmor.d/

# 2. load them in COMPLAIN mode first (logs violations, blocks nothing)
sudo apparmor_parser -r /etc/apparmor.d/pradyos-titan
sudo aa-complain /etc/apparmor.d/pradyos-titan      # repeat per profile

# 3. exercise the system, then read what each profile WOULD have blocked
sudo aa-logprof          # interactively tighten the allowlists from real logs

# 4. once clean, switch to ENFORCE
sudo aa-enforce /etc/apparmor.d/pradyos-*
```

## Wire into systemd

Add one line to each unit's `[Service]` section (kept out of this PR so the
shipped units are untouched until acceptance):

```ini
# pradyos-titan.service
AppArmorProfile=pradyos-titan
# pradyos-imperium.service
AppArmorProfile=pradyos-imperium
# pradyos-warden / oracle / throne / web .service
AppArmorProfile=pradyos-service
```

## Honest scope

AppArmor is path-based MAC; it raises the cost of a breakout and contains a
compromised daemon to its plane. It is **not** a sandbox against a kernel exploit,
and it never acts against the operator's machine — like the rest of the security
chain it confines *PradyOS itself*. Pair with the systemd directives already on
the units (do not remove those; AppArmor and seccomp/systemd are layers, not
substitutes).
