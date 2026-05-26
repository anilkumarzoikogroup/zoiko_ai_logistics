"""Root conftest.py — sys.path bootstrap for full-suite runs from the repo root.

Each phase's own conftest.py calls paths.py which does sys.path.insert(0, ...)
for that phase's directory.  When all phases run together those inserts can
reorder things so a later phase's 'services/' shadows an earlier phase's.

Important pytest lifecycle note:
  pytest_configure  → fires for root conftest only (before sub-conftest collection)
  pytest_sessionstart → fires BEFORE the collection phase
  Collection phase   → sub-directory conftest.py files are loaded HERE (can mess up sys.path)
  pytest_collection_finish → fires AFTER all conftest files have loaded

We hook pytest_collection_finish (not pytest_sessionstart) to re-establish the
correct canonical order after all per-phase conftest.py files have been loaded.
We also evict any cached 'services.*' modules so they get re-imported with the
correct path order during test execution.

Correct order for import resolution:
  phase-0/zoiko-common, phase-1, phase-1/kms, phase-2, phase-3, phase-4
so that phase-2's 'services' package is found before phase-3's.
"""
import sys
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))

_ORDERED_PATHS = [
    os.path.join(_ROOT, "phase-0", "packages", "zoiko-common"),
    os.path.join(_ROOT, "phase-1"),
    os.path.join(_ROOT, "phase-1", "packages", "zoiko-kms"),
    os.path.join(_ROOT, "phase-2"),
    os.path.join(_ROOT, "phase-3"),
    os.path.join(_ROOT, "phase-4"),
    os.path.join(_ROOT, "connector-hub"),
    os.path.join(_ROOT, "stub-service"),
]

# Module prefixes that are phase-specific and must be evicted after collection
# so they get re-imported with the correct (phase-2-first) sys.path order.
_EVICT_PREFIXES = ("services.", "shared.", "paths")


def _reorder_paths() -> None:
    """Remove managed paths from wherever they ended up, re-insert in canonical order."""
    for p in _ORDERED_PATHS:
        while p in sys.path:
            sys.path.remove(p)
    for p in reversed(_ORDERED_PATHS):
        sys.path.insert(0, p)


def _evict_service_modules() -> None:
    """Evict phase-specific cached modules so they re-import with corrected sys.path."""
    to_evict = [k for k in sys.modules if any(k == pfx.rstrip(".") or k.startswith(pfx)
                                               for pfx in _EVICT_PREFIXES)]
    for k in to_evict:
        del sys.modules[k]


def pytest_configure(config):
    _reorder_paths()


def pytest_sessionstart(session):
    _reorder_paths()


def pytest_collection_finish(session):
    """Re-establish correct path order AFTER all sub-phase conftest.py files have loaded."""
    _reorder_paths()
    _evict_service_modules()
