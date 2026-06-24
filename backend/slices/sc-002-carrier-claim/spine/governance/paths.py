"""Centralised sys.path bootstrap for sc-002's governance.  Import this first in every module."""
import sys, os

ROOT     = os.path.dirname(os.path.abspath(__file__))          # …/spine/governance
SPINE    = os.path.normpath(os.path.join(ROOT, ".."))           # …/spine
CORE     = os.path.join(SPINE, "core_lib")
PLATFORM = os.path.join(SPINE, "platform_lib")

for _p in [
    os.path.join(CORE, "packages", "zoiko-common"),
    PLATFORM,
    os.path.join(PLATFORM, "packages", "zoiko-kms"),
    ROOT,
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
