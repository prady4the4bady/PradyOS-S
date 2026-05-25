# PRADY OS — Sovereign Edition
# Multi-stage Dockerfile (Phase 9 — hardened)
#
# Stage 1: builder — install dependencies into /venv
# Stage 2: runtime — minimal image; non-root user; read-only-ready layout
#
# Security decisions:
#   - python:3.12-slim base (no OS-level package updates needed)
#   - Dedicated non-root user (uid/gid 1000) created in runtime stage
#   - Source + venv owned by pradyos via COPY --chown
#   - No SUID binaries installed; capabilities dropped at compose/run time
#   - /tmp is tmpfs when launched with --read-only (see docker-compose.yml)
#   - Secrets injected via environment variables from secrets files (never baked in)

FROM python:3.12-slim AS builder

WORKDIR /build

# Upgrade pip + wheel in one layer; no cache to keep image lean
RUN pip install --no-cache-dir "pip>=24.0" wheel

# Copy manifests first for cache-friendly dependency install
COPY pyproject.toml ./
COPY pradyos/__init__.py pradyos/

# Create isolated venv then install deps
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir -e ".[dev]" || \
    /venv/bin/pip install --no-cache-dir -e "."

# Copy full source and perform editable install
COPY . .
RUN /venv/bin/pip install --no-cache-dir -e .

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="PRADY OS Sovereign Edition"
LABEL org.opencontainers.image.description="Autonomous AI Operating System (Phase 9 hardened)"
LABEL org.opencontainers.image.vendor="PradyOS Project"

# Non-root operating user
RUN groupadd --gid 1000 pradyos && \
    useradd --uid 1000 --gid pradyos --shell /bin/bash --create-home pradyos && \
    mkdir -p /app/var/log /app/var/state /run/pradyos && \
    chown -R pradyos:pradyos /app /run/pradyos

# Venv + source owned by non-root user via --chown
COPY --from=builder --chown=pradyos:pradyos /venv /venv
COPY --from=builder --chown=pradyos:pradyos /build /app

WORKDIR /app

# Environment
ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PRADYOS_LOG_LEVEL=INFO \
    PRADYOS_ORACLE_PORT=11435

USER pradyos

# Sovereign web API (uvicorn) and ORACLE status endpoint
EXPOSE 8000
EXPOSE 11435

# Health check — hits the Sovereign metrics endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/metrics')" \
        || exit 1

# Default: run the sovereign web server
CMD ["/venv/bin/uvicorn", "pradyos.sovereign_web:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
