# PRADY OS — Sovereign Edition
# Multi-stage Dockerfile (Phase 7G)
#
# Stage 1: builder — install dependencies into a venv
# Stage 2: runtime — minimal image with only the venv + source

FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir pip==24.0 wheel

# Copy dependency manifest first (layer-cache friendly)
COPY pyproject.toml ./
COPY pradyos/__init__.py pradyos/

# Install runtime + optional deps into /venv
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir -e ".[dev]" || \
    /venv/bin/pip install --no-cache-dir -e "."

# Copy full source
COPY . .

# Install the package itself into the venv
RUN /venv/bin/pip install --no-cache-dir -e .

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="PRADY OS — Sovereign Edition"
LABEL org.opencontainers.image.description="Autonomous AI Operating System"

# Non-root user for security
RUN groupadd --gid 1000 pradyos && \
    useradd --uid 1000 --gid pradyos --shell /bin/bash --create-home pradyos

# Copy venv from builder
COPY --from=builder /venv /venv
COPY --from=builder /build /app

WORKDIR /app

# Ensure venv binaries are on PATH
ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PRADYOS_LOG_LEVEL=INFO

USER pradyos

# Sovereign web API (uvicorn)
EXPOSE 8000

# Health check — hits the metrics endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/metrics')" || exit 1

# Default: run the sovereign web server
CMD ["/venv/bin/uvicorn", "pradyos.sovereign_web:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
