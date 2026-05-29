#!/usr/bin/env python3
"""Phase 69 — Patch pradyos/sovereign_web.py (additive, surgical).

Three edits, none of which rewrite the file or touch the DASHBOARD_HTML line:
  1. Import  AnomalyDetector after the Phase 63 aggregate_root import.
  2. Add     `anomaly_detector: Any | None = None,` to create_app() signature.
  3. Insert  GET + POST /api/v1/anomaly endpoints immediately before `return app`.

All file I/O uses newline='' so existing LF line endings are preserved verbatim
(no accidental CRLF translation on Windows). Each anchor must occur exactly once;
the script aborts loudly on any mismatch and asserts the DASHBOARD_HTML line is
left untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_FILE = ROOT / "pradyos" / "sovereign_web.py"


# ── Edit 1: import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.aggregate_root import AggregateRegistry  # Phase 63\n"
NEW_IMPORT = (
    "from pradyos.core.aggregate_root import AggregateRegistry  # Phase 63\n"
    "from pradyos.core.anomaly_detector import AnomalyDetector  # Phase 69\n"
)

# ── Edit 2: create_app() signature param ────────────────────────────────────────
OLD_PARAM = "    job_scheduler: Any | None = None,\n) -> FastAPI:"
NEW_PARAM = (
    "    job_scheduler: Any | None = None,\n"
    "    anomaly_detector: Any | None = None,\n"
    ") -> FastAPI:"
)

# ── Edit 3: GET + POST /api/v1/anomaly endpoints before `return app` ─────────────
ANOMALY_ROUTES = '''    @app.get("/api/v1/anomaly")
    async def api_anomaly_get(request: Request) -> JSONResponse:
        if anomaly_detector is None:
            return JSONResponse({"error": "no anomaly detector configured"})
        signal = request.query_params.get("signal")
        if not signal:
            return JSONResponse({"error": "signal is required"})
        try:
            window = float(request.query_params.get("window", 3600))
        except (ValueError, TypeError):
            window = 3600.0
        use_cache = request.query_params.get("use_cache", "").lower() in ("1", "true", "yes")
        if use_cache:
            cached = anomaly_detector.get_cached(signal, window)
            if cached is not None:
                d = cached.to_dict()
                d["cached"] = True
                return JSONResponse(d)
        result = anomaly_detector.detect(signal, window=window)
        if use_cache:
            anomaly_detector.cache_result(result)
        d = result.to_dict()
        d["cached"] = False
        return JSONResponse(d)

    @app.post("/api/v1/anomaly")
    async def api_anomaly_post(request: Request) -> JSONResponse:
        if anomaly_detector is None:
            return JSONResponse({"error": "no anomaly detector configured"})
        body = await request.json()
        signal = body.get("signal")
        if not signal:
            return JSONResponse({"error": "signal is required"})
        try:
            window = float(body.get("window", 3600))
        except (ValueError, TypeError):
            window = 3600.0
        use_cache = bool(body.get("use_cache", False))
        if use_cache:
            cached = anomaly_detector.get_cached(signal, window)
            if cached is not None:
                d = cached.to_dict()
                d["cached"] = True
                return JSONResponse(d)
        result = anomaly_detector.detect(signal, window=window)
        if use_cache:
            anomaly_detector.cache_result(result)
        d = result.to_dict()
        d["cached"] = False
        return JSONResponse(d)'''

OLD_RETURN = '        return JSONResponse({"cancelled": True})\n\n    return app'
NEW_RETURN = (
    '        return JSONResponse({"cancelled": True})\n\n\n'
    + ANOMALY_ROUTES
    + "\n\n    return app"
)

EDITS = [
    ("import", OLD_IMPORT, NEW_IMPORT),
    ("signature param", OLD_PARAM, NEW_PARAM),
    ("anomaly routes", OLD_RETURN, NEW_RETURN),
]


def _dashboard_line_len(text: str) -> int:
    for line in text.split("\n"):
        if line.startswith("_DASHBOARD_HTML = "):
            return len(line)
    print("ERROR: could not locate _DASHBOARD_HTML line.", file=sys.stderr)
    sys.exit(1)


def patch() -> None:
    with open(WEB_FILE, "r", newline="") as fh:
        original = fh.read()

    if "anomaly_detector" in original:
        print("Already patched — 'anomaly_detector' present. Nothing to do.")
        return

    if "\r" in original:
        print("ERROR: file already contains CR bytes — refusing to patch.", file=sys.stderr)
        sys.exit(1)

    dash_len_before = _dashboard_line_len(original)
    lines_before = original.count("\n")
    expected_delta = 0

    text = original
    for name, old, new in EDITS:
        occurrences = text.count(old)
        if occurrences != 1:
            print(f"ERROR: anchor '{name}' found {occurrences} times (expected 1).",
                  file=sys.stderr)
            sys.exit(1)
        text = text.replace(old, new, 1)
        expected_delta += new.count("\n") - old.count("\n")

    # ── Integrity assertions ────────────────────────────────────────────────────
    lines_after = text.count("\n")
    actual_delta = lines_after - lines_before
    if actual_delta != expected_delta:
        print(f"ERROR: line-count delta {actual_delta} != expected {expected_delta}.",
              file=sys.stderr)
        sys.exit(1)

    if "\r" in text:
        print("ERROR: patch introduced CR bytes — aborting.", file=sys.stderr)
        sys.exit(1)

    dash_len_after = _dashboard_line_len(text)
    if dash_len_after != dash_len_before:
        print(f"ERROR: _DASHBOARD_HTML line length changed "
              f"({dash_len_before} -> {dash_len_after}).", file=sys.stderr)
        sys.exit(1)

    if "anomaly_detector" not in text or "/api/v1/anomaly" not in text:
        print("ERROR: expected content missing after patch.", file=sys.stderr)
        sys.exit(1)

    with open(WEB_FILE, "w", newline="") as fh:
        fh.write(text)

    print("Patched pradyos/sovereign_web.py successfully.")
    print(f"  lines: {lines_before} -> {lines_after} (+{actual_delta})")
    print(f"  _DASHBOARD_HTML line length unchanged: {dash_len_after}")


if __name__ == "__main__":
    patch()
