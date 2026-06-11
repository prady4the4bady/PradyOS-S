"""ORACLE — AI reasoning core for PRADY OS.

ORACLE connects to a local Ollama instance (qwen2.5:7b via HTTP),
receives tasks from IMPERIUM, produces structured TitanInstruction
execution plans, and routes approval-required items back to Sovereign
via the WARDEN GRID escalation path.

Public surface:
    Oracle                  — top-level facade
    OracleDaemon            — async main-loop daemon
    OllamaClient            — low-level HTTP client
    OraclePlanner           — task → TitanInstruction[] logic
"""

from pradyos.oracle.client import OllamaClient, OllamaError
from pradyos.oracle.oracle import Oracle
from pradyos.oracle.planner import OraclePlan, OraclePlanner

__all__ = [
    "OllamaClient",
    "OllamaError",
    "OraclePlanner",
    "OraclePlan",
    "Oracle",
]
