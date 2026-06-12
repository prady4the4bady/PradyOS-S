"""Shared HTTP helpers for the constellation web adapters.

Every plane's ``register_<plane>_routes`` adapter maps plane errors to HTTP
status codes the same way and parses request bodies the same way. These two
helpers are the single source of truth for that behaviour so the per-plane
adapters stay thin and consistent.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def err_response(exc: Exception) -> JSONResponse:
    """Map a plane error to 404 (unknown resource) or 422 (invalid input)."""
    code = 404 if "unknown" in str(exc) else 422
    return JSONResponse({"error": str(exc)}, status_code=code)


async def read_json(request: Request) -> Any:
    """Return the parsed JSON body, or ``None`` if the body is not valid JSON.

    A ``None`` return is treated by callers as "no usable body" and answered
    with a 422 — so any malformed payload degrades to a clean validation error
    rather than a 500.
    """
    try:
        return await request.json()
    except Exception:
        return None
