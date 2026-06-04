# Zoiko AI Logistics — Unified Backend (Phase 2 + Phase 4 on port 8000)

# ── Stage 1: install dependencies ─────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY phase-0/packages/zoiko-common/ ./phase-0/packages/zoiko-common/
COPY phase-1/packages/zoiko-kms/    ./phase-1/packages/zoiko-kms/
RUN pip install --no-cache-dir -e ./phase-0/packages/zoiko-common \
 && pip install --no-cache-dir -e ./phase-1/packages/zoiko-kms

# ── Stage 2: lean runtime ──────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    ZOIKO_DEV_MODE=false \
    ZOIKO_ISSUER=https://auth.zoikotech.com \
    OPA_URL="" \
    KAFKA_BOOTSTRAP="" \
    KAFKA_ENABLED=false \
    TOKEN_TTL_MINUTES=15 \
    JWT_TTL_SECONDS=3600

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deps /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=deps /usr/local/bin/ /usr/local/bin/

COPY phase-0/ ./phase-0/
COPY phase-1/ ./phase-1/
COPY phase-2/ ./phase-2/
COPY phase-3/ ./phase-3/
COPY phase-4/ ./phase-4/
COPY opa/     ./opa/

RUN useradd -r -u 1001 -s /sbin/nologin zoiko \
 && chown -R zoiko /app
USER zoiko

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Phase 2 app now includes Phase 4 routes — single port, Render-ready
CMD ["sh", "-c", "cd /app/phase-2 && python -m uvicorn services.api_gateway.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
