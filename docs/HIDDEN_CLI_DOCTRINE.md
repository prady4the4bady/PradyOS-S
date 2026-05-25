# The Hidden CLI Doctrine

> *If the user must routinely drop to a shell, the OS has failed to
> absorb machine labor.* — Blueprint §VII

Phase 0 enforces this at four levels:

## 1. Architectural

- `TitanExecutor.execute` calls `subprocess.Popen(argv, …, shell=False)`.
  There is no path through which a free-form shell string can reach the
  kernel without being parsed into an argv list first.
- The only sanctioned Sovereign entrypoint is
  `python -m pradyos.service` which boots the Throne. The systemd
  units boot the *services* directly — they never start a shell.

## 2. Constitutional

The `default_constitution()` (BASTION seed) classifies any of the
following as APPROVAL_REQUIRED:

- `rm -rf /…`, `mkfs`, `fdisk`, `dd if=`, `shred`, `wipefs`,
  `DROP TABLE`, `TRUNCATE TABLE`, `reboot`, `shutdown`, `halt`,
  `poweroff`, `systemctl stop/disable/mask pradyos-*`
- `scp … remote:`, `rclone copy … remote:`, `aws s3 cp … s3://`,
  `curl … -d @`, `gh release upload`
- `sudo passwd`, `usermod -aG sudo`, `chown root`, `chmod u+s`,
  `visudo`, `setuid`, `setgid`
- Any `kind` in `{project_proposal, constitution_change, policy_change,
  strategic_initiative, major_shift}`

These are escalated, not blocked silently. The Throne shows them as
pending approvals, with the matched rule and a `suggested_narrowing`.

## 3. Interface

The `Throne` class deliberately exposes only:

- `run(once: bool = False)`
- `approve(task_id, by="sovereign")`
- `reject(task_id, by="sovereign", reason="")`
- `stop()`

A unit test (`test_throne_hidden_cli_doctrine`) asserts that the
public surface contains no method named `exec`, `shell`, `system`,
`run_shell`, or `command`. CI will refuse to merge a PR that re-adds
one.

## 4. Operational

- Production deploys ship four systemd units (`pradyos-titan.service`,
  `pradyos-warden.service`, `pradyos-imperium.service`,
  `pradyos-throne.service`). None of them invokes a shell.
- The Throne is per-Sovereign-session and lives in `default.target`, not
  `multi-user.target` — it is launched on Sovereign login, not as a
  system daemon.

## When may the Sovereign open a shell?

Only for forensic drill-down (blueprint §VII). That path is
**optional and secondary**, and must remain a deliberate Sovereign
choice — never an unavoidable side effect of using the OS.
