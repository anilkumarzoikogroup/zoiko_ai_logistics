#!/bin/sh
# Start gateway (8000), governance (8002) and execution (8001) in one container

SPINE=/app/backend/slices/sc-001-freight-invoice-overcharge/spine

echo "[start.sh] Starting Gateway on port 8000..."
cd $SPINE/gateway && python -m uvicorn services.api_gateway.app:app \
  --host 0.0.0.0 --port 8000 --workers 2 &
P2_PID=$!

echo "[start.sh] Starting Governance on port 8002..."
cd $SPINE/governance && python -m uvicorn services.api_gateway.app:app \
  --host 0.0.0.0 --port 8002 --workers 2 &
P3_PID=$!

echo "[start.sh] Starting Execution on port 8001..."
cd $SPINE/execution && python -m uvicorn services.api_gateway.app:app \
  --host 0.0.0.0 --port 8001 --workers 2 &
P4_PID=$!

# Exit if any process dies
wait -n $P2_PID $P3_PID $P4_PID
EXIT_CODE=$?
echo "[start.sh] A service exited (code $EXIT_CODE). Shutting down..."
kill $P2_PID $P3_PID $P4_PID 2>/dev/null
exit $EXIT_CODE
