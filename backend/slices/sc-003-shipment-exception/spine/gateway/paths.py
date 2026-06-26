"""Centralised sys.path bootstrap for sc-003's gateway.  Import this first in every module."""
import sys, os

ROOT   = os.path.dirname(os.path.abspath(__file__))          # …/spine/gateway
SPINE  = os.path.normpath(os.path.join(ROOT, ".."))           # …/spine
SLICES = os.path.normpath(os.path.join(SPINE, "..", ".."))    # …/slices

CORE     = os.path.join(SPINE, "core_lib")
PLATFORM = os.path.join(SPINE, "platform_lib")

# SC-003 shares the same zoiko-common and platform libs as SC-002.
# Fall back to SC-002's spine if SC-003 doesn't have its own copies.
if not os.path.isdir(CORE):
    _SC002 = os.path.join(SLICES, "sc-002-carrier-claim", "spine")
    CORE     = os.path.join(_SC002, "core_lib")
    PLATFORM = os.path.join(_SC002, "platform_lib")

for _p in [
    os.path.join(CORE, "packages", "zoiko-common"),
    PLATFORM,
    os.path.join(PLATFORM, "packages", "zoiko-kms"),
    ROOT,
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
