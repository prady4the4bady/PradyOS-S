"""
scripts/patch_web_phase26.py
Phase 26 — wire PluginSandbox into sovereign_web.py

Changes applied (surgical string replacements only):
  1. Add `plugin_sandbox` parameter to create_app() signature.
  2. Add GET  /api/v1/plugins   endpoint.
  3. Add POST /api/v1/plugins/reload endpoint.

Run: python3 scripts/patch_web_phase26.py
"""
from pathlib import Path

WEB = Path("pradyos/sovereign_web.py")


def patch() -> None:
    src = WEB.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ #
    # 1. Add plugin_sandbox param to create_app() signature               #
    # ------------------------------------------------------------------ #
    OLD_SIG = "    replay_engine: Any | None = None,\n) -> FastAPI:"
    NEW_SIG = (
        "    replay_engine: Any | None = None,\n"
        "    plugin_sandbox: Any | None = None,\n"
        ") -> FastAPI:"
    )
    assert OLD_SIG in src, "Signature anchor not found — already patched?"
    src = src.replace(OLD_SIG, NEW_SIG, 1)

    # ------------------------------------------------------------------ #
    # 2. Insert plugin endpoints just before `return app`                 #
    # ------------------------------------------------------------------ #
    RETURN_APP = "    return app\n"
    NEW_ENDPOINTS = (
        "    @app.get(\"/api/v1/plugins\")\n"
        "    async def api_plugins_list() -> JSONResponse:\n"
        "        if plugin_sandbox is None:\n"
        "            return JSONResponse({\"plugins\": [], \"status\": {}})\n"
        "        return JSONResponse({\n"
        "            \"plugins\": [p.to_dict() for p in plugin_sandbox.get_plugins()],\n"
        "            \"status\": plugin_sandbox.status(),\n"
        "        })\n"
        "\n"
        "    @app.post(\"/api/v1/plugins/reload\")\n"
        "    async def api_plugins_reload() -> JSONResponse:\n"
        "        if plugin_sandbox is None:\n"
        "            return JSONResponse({\"reloaded\": 0, \"plugins\": []})\n"
        "        result = plugin_sandbox.reload_all()\n"
        "        return JSONResponse({\n"
        "            \"reloaded\": len(result),\n"
        "            \"plugins\": [p.to_dict() for p in result.values()],\n"
        "        })\n"
        "\n"
        "    return app\n"
    )
    assert RETURN_APP in src, "`return app` anchor not found"
    # Replace only the LAST occurrence (end of create_app)
    idx = src.rfind(RETURN_APP)
    src = src[:idx] + NEW_ENDPOINTS + src[idx + len(RETURN_APP):]

    WEB.write_text(src, encoding="utf-8")
    print(f"Patched {WEB}  ({src.count(chr(10))} lines total)")


if __name__ == "__main__":
    patch()
