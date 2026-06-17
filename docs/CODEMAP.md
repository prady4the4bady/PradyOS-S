# PradySovereign — Codemap (Structural Self-Knowledge)

The codemap plane uses AST analysis to give the agent — and its developers —
structural self-knowledge of the PradyOS codebase.  It is the OS looking at its own
source tree.

## API

| Function                          | Returns                                     |
|-----------------------------------|---------------------------------------------|
| `scan_package(root="pradyos/")`   | dict with `modules`, `total_modules`        |
| `export_json(root, output=None)`  | JSON string (writes to file if `output` set)|

Each module entry contains `functions`, `classes`, `methods`, `dependencies`,
and `loc`.

## CLI

```bash
pradyos-sovereign codemap              # print summary
pradyos-sovereign codemap --json       # export to codemap_index.json
```

## Mermaid Export

```bash
python scripts/export_codemap_mermaid.py                  # stdout
python scripts/export_codemap_mermaid.py -o arch           # arch.md
```

The Mermaid diagram shows packages as boxes with module/LOC counts, and
dependency edges between packages.

## Example

```
graph TD
  codemap[Codemap (2 modules, 187 LOC)]
  core[Core (86 modules, 12304 LOC)]
  guild[Guild (1 modules, 387 LOC)]
  skills[Skills (1 modules, 256 LOC)]
  dev_api[Dev Api (1 modules, 128 LOC)]
  codemap --> core
  guild --> core
  skills --> core
  dev_api --> guild
  dev_api --> skills
```

## Use Cases

- **Agent introspection**: the agent can query its own capabilities and structure
  at runtime.
- **Developer onboarding**: codemap summary tells you the full shape of the
  codebase in one command.
- **Documentation generation**: the Mermaid export feeds into Obsidian or
  GitHub-flavoured Markdown diagrams.
- **Dead-code analysis**: modules with zero functions or zero dependencies
  may be candidates for consolidation.
