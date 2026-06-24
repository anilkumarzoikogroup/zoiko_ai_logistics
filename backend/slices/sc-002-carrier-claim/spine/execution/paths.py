"""
Bootstrap sys.path so sc-002's execution modules can import core/platform packages
without installing them. Must be the FIRST import in every entry-point.
"""
import sys
import os

_EXECUTION = os.path.dirname(os.path.abspath(__file__))        # …/spine/execution
_SPINE     = os.path.normpath(os.path.join(_EXECUTION, ".."))  # …/spine

_PATHS = [
    os.path.join(_SPINE, "platform_lib", "packages", "zoiko-kms"),
    os.path.join(_SPINE, "platform_lib"),
    os.path.join(_SPINE, "core_lib", "packages", "zoiko-common"),
    _EXECUTION,
]

for _p in _PATHS:
    if _p not in sys.path:
        sys.path.insert(0, _p)
