#!/usr/bin/env bash
# Zoiko smoke test — verifies all three API gateways are running and healthy.
#
# Usage:
#   ./scripts/smoke-test.sh
#   BASE_URL=http://api.zoikotech.com ./scripts/smoke-test.sh
#
# Exits 0 if all checks pass, 1 otherwise.

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
P2_URL="${P2_URL:-${BASE_URL}:8000}"
P4_URL="${P4_URL:-${BASE_URL}:8001}"
HUB_URL="${HUB_URL:-${BASE_URL}:8010}"
STUB_URL="${STUB_URL:-${BASE_URL}:8013}"

PASS=0
FAIL=0

check() {
    local name="$1"
    local url="$2"
    local expected="$3"
    local response
    response=$(curl -sf --max-time 5 "$url" 2>/dev/null || true)
    if echo "$response" | grep -q "$expected"; then
        echo "[PASS] $name ($url)"
        PASS=$((PASS+1))
    else
        echo "[FAIL] $name ($url) — expected '$expected', got: $response"
        FAIL=$((FAIL+1))
    fi
}

echo "==> Zoiko smoke test — $(date)"
echo ""

check "Phase 2 health"       "$P2_URL/health"          '"status":"ok"'
check "Phase 2 version"      "$P2_URL/health"          '"version":"2.0.0"'
check "Phase 4 health"       "$P4_URL/health"          '"status":"ok"'
check "Connector Hub health" "$HUB_URL/health"         '"service":"connector-hub"'
check "Stub Service health"  "$STUB_URL/health"        '"service":"stub-service"'

# Check BlueDart connector is ACTIVE
CB=$(curl -sf --max-time 5 "$HUB_URL/v1/connectors/BlueDart/status" 2>/dev/null || true)
if echo "$CB" | grep -q '"ACTIVE"'; then
    echo "[PASS] BlueDart connector ACTIVE"
    PASS=$((PASS+1))
else
    echo "[FAIL] BlueDart connector status: $CB"
    FAIL=$((FAIL+1))
fi

echo ""
echo "==> Results: ${PASS} passed, ${FAIL} failed"
[ $FAIL -eq 0 ] && exit 0 || exit 1
