#!/usr/bin/env bash
# Zoiko ACR offline verifier — verify.sh
#
# Usage:
#   ./verify.sh acr.json
#   ./verify.sh acr_verify_<case_id>.json
#
# Requirements:
#   Python 3.10+ with cryptography package installed.
#
# Exit codes:
#   0 — PASS (Merkle root correct + signature valid)
#   1 — FAIL (tampered, wrong key, or malformed bundle)
#   2 — ERROR (missing file or dependency)
#
# This script is designed to be included inside the ACR verify zip package
# (acr_verify_<case_id>.zip) alongside acr.json, merkle_proof.json, and
# the public_keys/ directory.

set -euo pipefail

ACR_FILE="${1:-acr.json}"

if [ ! -f "$ACR_FILE" ]; then
  echo "ERROR: File not found: $ACR_FILE" >&2
  exit 2
fi

# Locate verifier.py — either alongside this script or in the repo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFIER=""

for candidate in \
  "$SCRIPT_DIR/verifier.py" \
  "$SCRIPT_DIR/phase-4/services/audit_acr_svc/verifier.py"; do
  if [ -f "$candidate" ]; then
    VERIFIER="$candidate"
    break
  fi
done

if [ -z "$VERIFIER" ]; then
  echo "ERROR: verifier.py not found. Place verify.sh alongside verifier.py." >&2
  exit 2
fi

# Ensure zoiko-common is importable
REPO_ROOT="$(cd "$SCRIPT_DIR" && git rev-parse --show-toplevel 2>/dev/null || echo "$SCRIPT_DIR")"
export PYTHONPATH="$REPO_ROOT/phase-0/packages/zoiko-common:$REPO_ROOT/phase-1:$REPO_ROOT/phase-1/packages/zoiko-kms:$REPO_ROOT/phase-4:${PYTHONPATH:-}"

echo "Verifying: $ACR_FILE"
echo "Verifier:  $VERIFIER"
echo "---"

python3 "$VERIFIER" "$ACR_FILE"
EXIT_CODE=$?

echo "---"
if [ $EXIT_CODE -eq 0 ]; then
  echo "RESULT: PASS — ACR is cryptographically valid."
else
  echo "RESULT: FAIL — ACR verification failed."
fi

exit $EXIT_CODE
