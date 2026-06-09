# Phase 3 — Governance/Evidence Gateway  (multi-stage, non-root user)
FROM python:3.10-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY phase-0/packages/zoiko-common/ /app/phase-0/packages/zoiko-common/
COPY phase-1/ /app/phase-1/
COPY phase-2/shared/ /app/phase-2/shared/
COPY phase-3/ /app/phase-3/

WORKDIR /app/phase-3
RUN adduser --disabled-password --no-create-home zoiko
USER zoiko

EXPOSE 8002
CMD ["python", "-m", "uvicorn", "services.api_gateway.app:app", \
     "--host", "0.0.0.0", "--port", "8002", "--workers", "2"]
