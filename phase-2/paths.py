"""Centralised sys.path bootstrap for Phase 2.  Import this first in every module."""
import sys, os

ROOT    = os.path.dirname(os.path.abspath(__file__))          # …/phase-2
PHASE_0 = os.path.normpath(os.path.join(ROOT, "..", "phase-0"))
PHASE_1 = os.path.normpath(os.path.join(ROOT, "..", "phase-1"))

for _p in [
    os.path.join(PHASE_0, "packages", "zoiko-common"),
    PHASE_1,
    os.path.join(PHASE_1, "packages", "zoiko-kms"),
    ROOT,
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
