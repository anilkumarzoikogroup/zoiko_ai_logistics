import paths  # noqa: F401
from zoiko_kms.local_backend import LocalKMSBackend

_backend = LocalKMSBackend()


def sign(tenant_slug: str, data: bytes) -> tuple[bytes, str]:
    kid = f"dev/{tenant_slug}-signing-v1"
    return _backend.sign(kid, data), kid


def verify(kid: str, data: bytes, signature: bytes) -> bool:
    return _backend.verify(kid, data, signature)
