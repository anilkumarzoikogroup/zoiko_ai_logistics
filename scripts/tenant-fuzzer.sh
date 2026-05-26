#!/usr/bin/env bash
# Tenant isolation fuzzer — submits cases from multiple tenants and verifies
# cross-tenant data leakage does NOT occur (T-007 equivalent).
#
# Usage:
#   ./scripts/tenant-fuzzer.sh
#   ROUNDS=10 ./scripts/tenant-fuzzer.sh

set -euo pipefail

PYTHON="${PYTHON:-python3}"
ROUNDS="${ROUNDS:-5}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export PYTHONPATH="$REPO_ROOT/phase-0/packages/zoiko-common:$REPO_ROOT/phase-1:$REPO_ROOT/phase-1/packages/zoiko-kms:$REPO_ROOT/phase-2:$REPO_ROOT/phase-3:$REPO_ROOT/phase-4"
export DB_URL="${DB_URL:-postgresql://postgres:1234@localhost/zoiko}"
export PYTHONIOENCODING=utf-8

echo "==> Tenant isolation fuzzer — $ROUNDS rounds"

$PYTHON "$REPO_ROOT/phase-0/scripts/tenant_fuzzer.py" --rounds "$ROUNDS"

echo "==> Fuzzer complete."
