# PradySovereign Enterprise Mode

Blueprint-driven multi-agent deployment with sovereign approval gates.

## Blueprint

Blueprints in `config/blueprints/` define agent capabilities, fleet topology, and
governance policies. See `config/blueprints/enterprise_agent.yaml` for the full schema.

## CLI

```bash
# Validate and stage an enterprise blueprint
pradyos-sovereign deploy enterprise_agent.yaml
```

## Demo

```bash
python scripts/demo_enterprise_deployment.py
```

Simulates: blueprint load → replica deployment (with Sovereign proposals) →
multi-role fleet task → synthesis.
All decisions are logged to the Decision Journal.
