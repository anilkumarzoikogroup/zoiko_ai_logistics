#!/bin/sh
# Start Phase 2 (port 8000) and Phase 4 (port 8001) in one container

echo "[start.sh] Starting Phase 2 on port 8000..."
cd /app/phase-2 && python -m uvicorn services.api_gateway.app:app \
  --host 0.0.0.0 --port 8000 --workers 2 &
P2_PID=$!

echo "[start.sh] Starting Phase 4 on port 8001..."
cd /app/phase-4 && python -m uvicorn services.api_gateway.app:app \
  --host 0.0.0.0 --port 8001 --workers 2 &
P4_PID=$!

# Exit if either process dies
wait -n $P2_PID $P4_PID
EXIT_CODE=$?
echo "[start.sh] A service exited (code $EXIT_CODE). Shutting down..."
kill $P2_PID $P4_PID 2>/dev/null
exit $EXIT_CODE
