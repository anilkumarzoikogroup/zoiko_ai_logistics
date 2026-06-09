"""Centralised sys.path bootstrap for backend/gateway.  Import this first in every module."""
import sys, os

ROOT     = os.path.dirname(os.path.abspath(__file__))          # …/backend/gateway
CORE     = os.path.normpath(os.path.join(ROOT, "..", "core"))
PLATFORM = os.path.normpath(os.path.join(ROOT, "..", "platform"))

for _p in [
    os.path.join(CORE, "packages", "zoiko-common"),
    PLATFORM,
    os.path.join(PLATFORM, "packages", "zoiko-kms"),
    ROOT,
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
