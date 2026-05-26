# Phase 2 — API Gateway  (multi-stage, non-root user)
FROM python:3.10-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps from root requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY phase-0/packages/zoiko-common/ /app/phase-0/packages/zoiko-common/
COPY phase-1/ /app/phase-1/
COPY phase-2/ /app/phase-2/

WORKDIR /app/phase-2
RUN adduser --disabled-password --no-create-home zoiko
USER zoiko

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "services.api_gateway.app:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
