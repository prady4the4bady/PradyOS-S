"""Phase 22 patch script — adds MetricsRegistry wiring to sovereign_web.py.

Patches:
  1. Adds PlainTextResponse to the fastapi.responses import.
  2. Adds `metrics` optional param to create_app().
  3. Inserts GET /metrics and GET /api/v1/metrics endpoints before `return app`.

NEVER rewrites the file — operates purely via str.replace().
Safe to run multiple times (idempotent guards on each patch).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "pradyos" / "sovereign_web.py"


def patch(text: str) -> str:
    # ------------------------------------------------------------------
    # 1. Add PlainTextResponse to the fastapi.responses import if absent
    # ------------------------------------------------------------------
    old_import = "from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse"
    new_import = (
        "from fastapi.responses import HTMLResponse, JSONResponse, "
        "PlainTextResponse, StreamingResponse"
    )
    if "PlainTextResponse" not in text:
        assert old_import in text, "Could not find fastapi.responses import line"
        text = text.replace(old_import, new_import, 1)

    # ------------------------------------------------------------------
    # 2. Add `metrics` param to create_app() signature
    # ------------------------------------------------------------------
    old_sig = "    config_reloader: Any | None = None,\n) -> FastAPI:"
    new_sig = (
        "    config_reloader: Any | None = None,\n"
        "    metrics: Any | None = None,\n"
        ") -> FastAPI:"
    )
    if "    metrics: Any | None = None," not in text:
        assert old_sig in text, "Could not find config_reloader param in create_app() signature"
        text = text.replace(old_sig, new_sig, 1)

    # ------------------------------------------------------------------
    # 3. Insert /metrics and /api/v1/metrics endpoints just before `return app`
    #    Anchor: the unique closing pattern of the config_reloader block
    # ------------------------------------------------------------------
    old_return = "            status_code=200,\n        )\n\n    return app\n"
    new_return = (
        "            status_code=200,\n"
        "        )\n"
        "\n"
        "    @app.get(\"/metrics\", include_in_schema=False)\n"
        "    async def prometheus_metrics() -> PlainTextResponse:\n"
        "        if metrics is None:\n"
        "            return PlainTextResponse(\n"
        "                \"\",\n"
        "                media_type=\"text/plain; version=0.0.4; charset=utf-8\",\n"
        "            )\n"
        "        return PlainTextResponse(\n"
        "            metrics.render_prometheus(),\n"
        "            media_type=\"text/plain; version=0.0.4; charset=utf-8\",\n"
        "        )\n"
        "\n"
        "    @app.get(\"/api/v1/metrics\")\n"
        "    async def api_metrics() -> JSONResponse:\n"
        "        if metrics is None:\n"
        "            return JSONResponse({})\n"
        "        return JSONResponse(metrics.get_all())\n"
        "\n"
        "    return app\n"
    )
    if '"/metrics"' not in text:
        assert old_return in text, (
            "Could not find config_reloader closing + return app anchor.\n"
            f"Looking for: {repr(old_return)}"
        )
        text = text.replace(old_return, new_return, 1)

    return text


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    patched = patch(original)
    if patched == original:
        print("sovereign_web.py already patched — nothing to do.")
        return
    TARGET.write_text(patched, encoding="utf-8")
    print(f"Patched {TARGET} successfully.")


if __name__ == "__main__":
    main()
