# PradySovereign Local Personal Mode

Run a governed personal assistant daemon that listens on a local HTTP endpoint.

## Quickstart

```bash
# Start the daemon with the default personal-assistant blueprint
pradyos-sovereign daemon

# Or specify a custom blueprint
pradyos-sovereign daemon --blueprint my_blueprint.yaml --port 8080
```

## Blueprint Schema

Blueprints live in `config/blueprints/` and define agent capabilities:

```yaml
agent_name: "personal-assistant"
tools:
  filesystem:
    root: "./sandbox"
    allowed_ops: ["read", "write", "list"]
  email:
    domains: ["example.com"]
    max_per_hour: 50
sovereign_policies:
  min_risk_for_manual_approval: 0.7
  log_all_actions: true
```

## End-to-End Demo

```bash
python scripts/demo_personal_assistant.py
```

Simulates: read inbox → summarise → propose calendar event → draft reply.
All actions are logged via SovereignClient into the Decision Journal.
