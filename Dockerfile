# Zoiko AI Logistics — Backend image (Render)
#
# This single image contains all three backend services (gateway, governance,
# execution). Which one runs is decided by CMD — Render services override this
# via `dockerCommand` in render.yaml. Default CMD runs the API gateway.

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

COPY backend/slices/sc-001-freight-invoice-overcharge/spine/core_lib/packages/zoiko-common/  ./backend/slices/sc-001-freight-invoice-overcharge/spine/core_lib/packages/zoiko-common/
COPY backend/slices/sc-001-freight-invoice-overcharge/spine/platform_lib/packages/zoiko-kms/ ./backend/slices/sc-001-freight-invoice-overcharge/spine/platform_lib/packages/zoiko-kms/
RUN pip install --no-cache-dir -e ./backend/slices/sc-001-freight-invoice-overcharge/spine/core_lib/packages/zoiko-common \
 && pip install --no-cache-dir -e ./backend/slices/sc-001-freight-invoice-overcharge/spine/platform_lib/packages/zoiko-kms

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

COPY backend/      ./backend/
COPY opa/          ./opa/
COPY alembic.ini   ./alembic.ini

RUN useradd -r -u 1001 -s /sbin/nologin zoiko \
 && chown -R zoiko /app
USER zoiko

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Default: API Gateway on $PORT (Render injects PORT)
CMD ["sh", "-c", "cd /app/backend/slices/sc-001-freight-invoice-overcharge/spine/gateway && python -m uvicorn services.api_gateway.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
