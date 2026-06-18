# Commands Cheat Sheet

## A) Install & Setup

```bash
git clone https://github.com/prady4the4bady/PradyOS-S
cd PradyOS-S

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Install package in editable mode
pip install -e .
```

No environment variables are required for offline/demo mode. The LLM provider
defaults to a local stub when no endpoint is configured.

## B) Dev Mode

```bash
# Skill engine demo: learn -> run -> reinforce -> match
python examples/hello_skill.py

# 6-role multi-agent bugfix simulation
python examples/swarm_bugfix.py

# Guild swarm introspects the actual repo via codemap
python examples/swarm_on_repo.py --task "Find one small improvement in this repo and propose a patch."
```

## C) Local Personal Mode

```bash
# Start the sovereign daemon with personal assistant blueprint
pradyos-sovereign daemon --blueprint config/blueprints/personal_assistant.yaml

# Run the personal assistant demo (separate terminal)
python scripts/demo_personal_assistant.py

# Stop the daemon with Ctrl+C
```

## D) Enterprise / Docker Mode

```bash
# Start the full stack (sovereign + oracle + admission + redis)
docker-compose -f deploy/docker-compose.yml up -d

# Check health via metrics endpoint
curl http://localhost:8000/api/metrics

# Alternative: JSON metrics
curl http://localhost:8000/api/v1/metrics

# Tear down
docker-compose -f deploy/docker-compose.yml down
```

## E) Testing & Benchmarks

```bash
# Proving ground — runs the canonical test module list
python scripts/prove.py

# Proving ground with benchmarks
python scripts/prove.py --benchmark

# Benchmarks only (structured JSON output)
python scripts/benchmarks.py --json

# List available benchmarks
python scripts/benchmarks.py --list

# Full pytest suite (20-25 min on typical hardware)
pytest tests/ -x --tb=short -q

# Targeted subsets (examples)
pytest tests/test_core.py tests/test_bloom_filter.py -x --tb=short -q
pytest tests/test_semantic_memory.py tests/test_novelty_detector.py -x --tb=short -q
```

## F) Codemap & Graph

```bash
# Print codebase summary
pradyos-sovereign codemap

# Export codemap as JSON
pradyos-sovereign codemap --json

# Generate Mermaid dependency graph
python scripts/export_codemap_mermaid.py

# Write graph to file
python scripts/export_codemap_mermaid.py -o filename
```

## H) Billing & Licensing

```bash
# View pricing page
curl http://localhost:8000/billing

# Check current tier and entitlements
curl http://localhost:8000/api/v1/license/status

# Check a specific feature
curl "http://localhost:8000/api/v1/license/entitled?feature=blueprint_manager"

# Start checkout for a paid tier
curl -X POST http://localhost:8000/api/v1/billing/checkout \
  -H "Content-Type: application/json" \
  -d '{"tier": "pro"}'

# Manually activate a tier (dev testing / enterprise key entry)
curl -X POST http://localhost:8000/api/v1/license/activate \
  -H "Content-Type: application/json" \
  -d '{"tier": "sovereign"}'

# Install a signed license key
curl -X POST http://localhost:8000/api/v1/license/install \
  -H "Content-Type: application/json" \
  -d '{"token": "<signed-license-token>"}'

# Reset to free tier
curl -X DELETE http://localhost:8000/api/v1/license/reset

# Set up Stripe product catalogue
python scripts/stripe_setup.py
```

## J) Deployment

```bash
# Render (free tier)
# Connect repo at https://render.com — render.yaml is auto-detected

# Fly.io
fly launch    # uses fly.toml
fly deploy

# Docker
docker-compose -f deploy/docker-compose.yml up -d

# Manual cold-start
uvicorn pradyos.sovereign_web:create_app --factory --host 0.0.0.0 --port 8000

# Verify health
curl http://localhost:8000/health
```

## K) CLI Reference

```bash
pradyos-sovereign --help              # All commands
pradyos-sovereign status              # System status
pradyos-sovereign approve <id>        # Approve a decision
pradyos-sovereign reject <id>         # Reject a decision
pradyos-sovereign run-campaign <name> # Execute a campaign
```
