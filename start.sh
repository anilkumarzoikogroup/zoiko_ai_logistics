#!/bin/bash
# Start backend/gateway (8000), backend/governance (8002) and backend/execution (8001) in one container

echo "[start.sh] Starting Gateway on port 8000..."
cd /app/backend/gateway && python -m uvicorn services.api_gateway.app:app \
  --host 0.0.0.0 --port 8000 --workers 2 &
P2_PID=$!

echo "[start.sh] Starting Governance on port 8002..."
cd /app/backend/governance && python -m uvicorn services.api_gateway.app:app \
  --host 0.0.0.0 --port 8002 --workers 2 &
P3_PID=$!

echo "[start.sh] Starting Execution on port 8001..."
cd /app/backend/execution && python -m uvicorn services.api_gateway.app:app \
  --host 0.0.0.0 --port 8001 --workers 2 &
P4_PID=$!

# Exit if any process dies
wait -n $P2_PID $P3_PID $P4_PID
EXIT_CODE=$?
echo "[start.sh] A service exited (code $EXIT_CODE). Shutting down..."
kill $P2_PID $P3_PID $P4_PID 2>/dev/null
exit $EXIT_CODE
