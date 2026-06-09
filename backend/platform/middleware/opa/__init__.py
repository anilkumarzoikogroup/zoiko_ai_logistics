"""OPA policy client and FastAPI middleware."""
from .client import OPAClient, OPADecision
from .middleware import OPAMiddleware

__all__ = ["OPAClient", "OPADecision", "OPAMiddleware"]
