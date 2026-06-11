# PRADY OS Phase 0 base image
FROM python:3.11-slim

WORKDIR /app

# Substrate tools TITAN OPS may invoke
RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    util-linux \
    iproute2 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pradyos ./pradyos
COPY README.md ./
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/var/log /app/var/state /run/pradyos

CMD ["python", "-m", "pradyos.service"]
