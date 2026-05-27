from __future__ import annotations

import time
from typing import Any

VERSION = "0.40.0"

# Map module attribute → introspection method name.
# Module names align with create_app() params; CorrelationEngine
# has no introspection method — its summary will be {}.
_INTROSPECTION = {
    "health_scorecard":   "get_report",
    "signal_aggregator":  "list_signals",
    "task_scheduler":     "count",
    "memory_store":       "count",
    "healing_monitor":    "count",
    "snapshot_store":     "count",
    "reactor_engine":     "count",
    "state_manager":      "status",
    "watchpoint_system":  "status",
    "correlation_engine": "_no_method",  # intentionally absent
    "integration_bus":    "status",
}


class ControlPlane:
    def __init__(
        self,
        health_scorecard=None,
        signal_aggregator=None,
        task_scheduler=None,
        memory_store=None,
        healing_monitor=None,
        snapshot_store=None,
        reactor_engine=None,
        state_manager=None,
        watchpoint_system=None,
        correlation_engine=None,
        integration_bus=None,
    ) -> None:
        self._start_time = time.time()
        self._modules: dict[str, Any] = {
            "health_scorecard":   health_scorecard,
            "signal_aggregator":  signal_aggregator,
            "task_scheduler":     task_scheduler,
            "memory_store":       memory_store,
            "healing_monitor":    healing_monitor,
            "snapshot_store":     snapshot_store,
            "reactor_engine":     reactor_engine,
            "state_manager":      state_manager,
            "watchpoint_system":  watchpoint_system,
            "correlation_engine": correlation_engine,
            "integration_bus":    integration_bus,
        }

    def uptime(self) -> float:
        return time.time() - self._start_time

    def _safe_summary(self, module, method: str) -> dict:
        if module is None:
            return {}
        try:
            fn = getattr(module, method, None)
            if fn is None or not callable(fn):
                return {}
            result = fn()
            if isinstance(result, dict):
                return result
            if hasattr(result, "to_dict"):
                td = result.to_dict()
                if isinstance(td, dict):
                    return td
                return {"value": td}
            return {"value": result}
        except Exception as exc:
            return {"error": str(exc)}

    def status(self) -> dict:
        modules_out: dict[str, dict] = {}
        for name, mod in self._modules.items():
            present = mod is not None
            method = _INTROSPECTION.get(name, "")
            summary = self._safe_summary(mod, method) if present else {}
            modules_out[name] = {"present": present, "summary": summary}
        return {
            "os_version": VERSION,
            "uptime_seconds": self.uptime(),
            "modules": modules_out,
        }

    def tick(self) -> dict:
        result = {"ticks": [], "healed": [], "reactions": []}

        scheduler = self._modules.get("task_scheduler")
        if scheduler is not None:
            try:
                runs = scheduler.tick()
                result["ticks"] = [r.to_dict() if hasattr(r, "to_dict") else r for r in runs]
            except Exception:
                result["ticks"] = []

        healer = self._modules.get("healing_monitor")
        if healer is not None:
            try:
                events = healer.check_and_heal()
                result["healed"] = [e.to_dict() if hasattr(e, "to_dict") else e for e in events]
            except Exception:
                result["healed"] = []

        reactor = self._modules.get("reactor_engine")
        if reactor is not None:
            try:
                reactions = reactor.react({})
                result["reactions"] = [
                    r.to_dict() if hasattr(r, "to_dict") else r for r in reactions
                ]
            except Exception:
                result["reactions"] = []

        return result
