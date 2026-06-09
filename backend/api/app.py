"""
backend/api — clean frontend-facing API entry point.

This is the single surface that the React frontend (port 5173) talks to.
It reverse-proxies all requests to the correct backend service:

  /v1/auth/*        → gateway (port 8000)
  /v1/cases/*       → gateway (port 8000)
  /v1/connectors/*  → gateway (port 8000)
  /v1/reports/*     → gateway (port 8000)
  /v1/evidence/*    → governance (port 8002)
  /v1/tokens/*      → governance (port 8002)
  /v1/execute       → execution (port 8001)
  /v1/reconcile     → execution (port 8001)

Run (dev):
    cd backend/api
    python -m uvicorn app:app --reload --host 0.0.0.0 --port 8080

In production, use a proper reverse proxy (nginx / AWS ALB) instead of this
Python layer. This file exists for local dev convenience.
"""
import os
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

GATEWAY_URL    = os.getenv("GATEWAY_URL",    "http://localhost:8000")
GOVERNANCE_URL = os.getenv("GOVERNANCE_URL", "http://localhost:8002")
EXECUTION_URL  = os.getenv("EXECUTION_URL",  "http://localhost:8001")

CORS_ORIGINS = os.getenv("ZOIKO_CORS_ORIGINS", "http://localhost:5173").split(",")

app = FastAPI(
    title="Zoiko API",
    description="Frontend-facing API — routes requests to internal backend services",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_GOVERNANCE_PREFIXES = (
    "/v1/evidence",
    "/v1/tokens",
    "/governance",
)

_EXECUTION_PREFIXES = (
    "/v1/execute",
    "/v1/reconcile",
    "/v1/cases/{id}/acr",
    "/execution",
)


def _route(path: str) -> str:
    for prefix in _GOVERNANCE_PREFIXES:
        if path.startswith(prefix.split("{")[0]):
            return GOVERNANCE_URL
    for prefix in _EXECUTION_PREFIXES:
        if path.startswith(prefix.split("{")[0]):
            return EXECUTION_URL
    return GATEWAY_URL


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy(request: Request, path: str) -> Response:
    full_path = "/" + path
    if request.query_string:
        full_path += "?" + request.query_string.decode()

    target = _route(full_path)
    url = target + full_path

    headers = dict(request.headers)
    headers.pop("host", None)

    body = await request.body()

    async with httpx.AsyncClient(timeout=60.0) as client:
        upstream = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=dict(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "zoiko-api", "version": "1.0.0"}
