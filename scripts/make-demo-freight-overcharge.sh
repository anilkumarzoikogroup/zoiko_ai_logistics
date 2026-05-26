#!/usr/bin/env bash
# SC-001 end-to-end demo script — BlueDart overcharge detection.
#
# This is the script invoked by `make demo-freight-overcharge`.
# Runs all three phase demos in sequence and prints a summary.
#
# Usage:
#   ./scripts/make-demo-freight-overcharge.sh
#   ROUNDS=100 ./scripts/make-demo-freight-overcharge.sh  (T-001: 100 consecutive runs)

set -euo pipefail

PYTHON="${PYTHON:-python3}"
ROUNDS="${ROUNDS:-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export DB_URL="${DB_URL:-postgresql://postgres:1234@localhost/zoiko}"
export PYTHONIOENCODING=utf-8
export ZOIKO_DEV_MODE=true
export ZOIKO_DEV_SECRET=zoiko-dev-secret-for-testing-only
export PYTHONPATH="$REPO_ROOT/phase-0/packages/zoiko-common:$REPO_ROOT/phase-1:$REPO_ROOT/phase-1/packages/zoiko-kms:$REPO_ROOT/phase-2:$REPO_ROOT/phase-3:$REPO_ROOT/phase-4"

PASS=0
FAIL=0

for i in $(seq 1 "$ROUNDS"); do
    echo ""
    echo "==> SC-001 run $i/$ROUNDS"
    if $PYTHON "$REPO_ROOT/phase-2/demo_phase2.py" && \
       $PYTHON "$REPO_ROOT/phase-3/demo_phase3.py" && \
       $PYTHON "$REPO_ROOT/phase-4/demo_phase4.py"; then
        PASS=$((PASS+1))
        echo "    [PASS] Run $i"
    else
        FAIL=$((FAIL+1))
        echo "    [FAIL] Run $i"
    fi
done

echo ""
echo "==> SC-001 summary: $PASS/$ROUNDS passed, $FAIL failed"
[ $FAIL -eq 0 ] && exit 0 || exit 1
