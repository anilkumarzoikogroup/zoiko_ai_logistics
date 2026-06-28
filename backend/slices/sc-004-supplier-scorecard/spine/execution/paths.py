"""Bootstrap sys.path for sc-004's execution spine. Import first in every module."""
import sys, os

_EXECUTION = os.path.dirname(os.path.abspath(__file__))        # …/spine/execution
_SPINE     = os.path.normpath(os.path.join(_EXECUTION, ".."))  # …/spine
_SLICES    = os.path.normpath(os.path.join(_SPINE, "..", ".."))

_CORE     = os.path.join(_SPINE, "core_lib")
_PLATFORM = os.path.join(_SPINE, "platform_lib")

# Fall back to SC-002's libraries if SC-004 doesn't have its own copies.
if not os.path.isdir(_CORE):
    _SC002    = os.path.join(_SLICES, "sc-002-carrier-claim", "spine")
    _CORE     = os.path.join(_SC002, "core_lib")
    _PLATFORM = os.path.join(_SC002, "platform_lib")

for _p in [
    os.path.join(_CORE, "packages", "zoiko-common"),
    _PLATFORM,
    os.path.join(_PLATFORM, "packages", "zoiko-kms"),
    _EXECUTION,
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
