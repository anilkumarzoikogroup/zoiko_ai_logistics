"""
Bootstrap sys.path so phase-4 modules can import phase-0/1/3 packages
without installing them. Must be the FIRST import in every entry-point.

Added to sys.path:
  - phase-4/           (local services, shared)
  - phase-0/packages/zoiko-common/   (zoiko_common)
  - phase-1/           (kafka, middleware, zoiko_kms)
  - phase-1/packages/zoiko-kms/      (zoiko_kms)
  - phase-3/           (redis_token.py re-used for consumed lock)
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PATHS = [
    os.path.join(_ROOT, "phase-4"),
    os.path.join(_ROOT, "phase-0", "packages", "zoiko-common"),
    os.path.join(_ROOT, "phase-1"),
    os.path.join(_ROOT, "phase-1", "packages", "zoiko-kms"),
    os.path.join(_ROOT, "phase-3"),   # for shared/redis_token.py
]

for _p in _PATHS:
    if _p not in sys.path:
        sys.path.insert(0, _p)
