import paths  # noqa: F401
from zoiko_kms.local_backend import LocalKMSBackend
_backend = LocalKMSBackend()
def sign(tenant_slug: str, data: bytes) -> tuple:
    kid = f"dev/{tenant_slug}-signing-v1"
    return _backend.sign(kid, data), kid
