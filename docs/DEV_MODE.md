# PradySovereign Dev Mode

The Dev API provides high-level facades for building agent applications:

## SkillEngine (L1)
- **`register_skill(name, prompt, tools)`** — Register a reusable skill.
- **`run_skill(name, input)`** — Retrieve a skill definition for execution.

Maps to: `pradyos.skills.library` (L1 competence layer).

## GuildSwarm (L2/L3/L5)
- **`add_agent(role, tools)`** — Register a specialist role.
- **`run_task(task_description)`** — Run a multi-agent workflow.

Maps to: `pradyos.guild.org` (multi-agent orchestration).

## SovereignClient (Governance)
- **`submit_proposal(payload)`** — Propose an action to the Sovereign.
- **`log_decision(decision)`** — Record a Sovereign decision.

Maps to: `pradyos.sovereign.cli` (governance interface).

## Layer Mapping
- **L1 (Competence)**: SkillEngine
- **L2 (Foresight)**: Swarm execution patterns
- **L3 (Drive)**: Task initiation via GuildSwarm
- **L5 (Causality)**: Execution trace capture
