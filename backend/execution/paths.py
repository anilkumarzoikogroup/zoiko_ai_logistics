"""
Bootstrap sys.path so backend/execution modules can import core/platform/governance packages
without installing them. Must be the FIRST import in every entry-point.

Added to sys.path:
  - backend/execution/              (local services, shared)
  - backend/core/packages/zoiko-common/   (zoiko_common)
  - backend/platform/               (kafka, middleware, zoiko_kms)
  - backend/platform/packages/zoiko-kms/ (zoiko_kms)
  - backend/governance/             (redis_token.py re-used for consumed lock)
"""
import sys
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PATHS = [
    os.path.join(_BACKEND, "governance"),   # for shared/redis_token.py
    os.path.join(_BACKEND, "platform", "packages", "zoiko-kms"),
    os.path.join(_BACKEND, "platform"),
    os.path.join(_BACKEND, "core", "packages", "zoiko-common"),
    os.path.join(_BACKEND, "execution"),
]

# Inserted in this order so that, after all insert(0,...) calls, backend/execution
# ends up FIRST in sys.path — its "services"/"shared" packages must win over the
# same-named namespace packages in backend/governance.
for _p in _PATHS:
    if _p not in sys.path:
        sys.path.insert(0, _p)
