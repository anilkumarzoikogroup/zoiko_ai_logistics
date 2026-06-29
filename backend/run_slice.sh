#!/bin/sh
# Generic per-slice service launcher for Render.
# Usage: sh /app/backend/run_slice.sh <relative-path-to-spine-subdir>
# Keeps render.yaml's dockerCommand to two plain tokens (no &&, quotes, or
# $VAR expansion in the YAML string itself) so it can't be mis-tokenized.
cd "/app/$1" || exit 1
exec python -m uvicorn services.api_gateway.app:app --host 0.0.0.0 --port "$PORT" --workers 2
