# Phase 4 — Execution Gateway  (multi-stage, non-root user)
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
COPY phase-3/shared/ /app/phase-3/shared/
COPY phase-4/ /app/phase-4/

WORKDIR /app/phase-4
RUN adduser --disabled-password --no-create-home zoiko
USER zoiko

EXPOSE 8001
CMD ["python", "-m", "uvicorn", "services.api_gateway.app:app", \
     "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
