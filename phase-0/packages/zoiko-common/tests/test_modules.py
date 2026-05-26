"""Tests for signing, auth, idempotency, kafka, and observability modules."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from zoiko_common.auth import ZoikoClaims, TenantMismatchError, assert_tenant_binding
from zoiko_common.crypto.signing import (
    LocalEd25519Backend,
    ZoikoSigner,
    SignedEnvelope,
    verify_envelope,
    COSE_ALG_EDDSA,
)
from zoiko_common.kafka import partition_key, KafkaMessage, TOPICS
from zoiko_common.idempotency import IdempotencyStore, IdempotencyStatus


# ---------------------------------------------------------------------------
# signing.py
# ---------------------------------------------------------------------------


class TestLocalEd25519Backend:
    def test_kid_has_local_prefix(self):
        b = LocalEd25519Backend()
        assert b.kid.startswith("local:")

    def test_kid_is_deterministic_for_same_key(self):
        b = LocalEd25519Backend()
        assert b.kid == b.kid

    def test_two_backends_have_different_kids(self):
        a = LocalEd25519Backend()
        b = LocalEd25519Backend()
        assert a.kid != b.kid

    def test_sign_returns_64_bytes(self):
        b = LocalEd25519Backend()
        sig = b.sign(b"hello")
        assert len(sig) == 64

    def test_public_key_der_is_bytes(self):
        b = LocalEd25519Backend()
        der = b.public_key_der()
        assert isinstance(der, bytes)
        assert len(der) > 0


class TestZoikoSigner:
    def test_sign_returns_envelope(self):
        signer = ZoikoSigner(LocalEd25519Backend())
        env = signer.sign(b"payload")
        assert isinstance(env, SignedEnvelope)
        assert env.payload == b"payload"
        assert len(env.signature) == 64
        assert env.alg == COSE_ALG_EDDSA

    def test_kid_exposed(self):
        backend = LocalEd25519Backend()
        signer = ZoikoSigner(backend)
        assert signer.kid == backend.kid

    def test_public_key_der_exposed(self):
        signer = ZoikoSigner(LocalEd25519Backend())
        assert isinstance(signer.public_key_der, bytes)


class TestVerifyEnvelope:
    def test_valid_signature_returns_true(self):
        signer = ZoikoSigner(LocalEd25519Backend())
        env = signer.sign(b"hello world")
        assert verify_envelope(env, signer.public_key_der)

    def test_tampered_payload_returns_false(self):
        signer = ZoikoSigner(LocalEd25519Backend())
        env = signer.sign(b"original")
        tampered = SignedEnvelope(
            payload=b"tampered",
            signature=env.signature,
            kid=env.kid,
        )
        assert not verify_envelope(tampered, signer.public_key_der)

    def test_wrong_public_key_returns_false(self):
        signer_a = ZoikoSigner(LocalEd25519Backend())
        signer_b = ZoikoSigner(LocalEd25519Backend())
        env = signer_a.sign(b"data")
        assert not verify_envelope(env, signer_b.public_key_der)


class TestSignedEnvelopeRoundtrip:
    def test_to_from_dict(self):
        signer = ZoikoSigner(LocalEd25519Backend())
        original = signer.sign(b"roundtrip test")
        restored = SignedEnvelope.from_dict(original.to_dict())
        assert restored.payload == original.payload
        assert restored.signature == original.signature
        assert restored.kid == original.kid
        assert restored.alg == original.alg


# ---------------------------------------------------------------------------
# auth/__init__.py
# ---------------------------------------------------------------------------


class TestZoikoClaims:
    def test_from_jwt_payload_minimal(self):
        payload = {"sub": "user-123", "zoiko_tenant": "t-abc"}
        claims = ZoikoClaims.from_jwt_payload(payload)
        assert claims.sub == "user-123"
        assert claims.tenant_id == "t-abc"
        assert claims.email is None
        assert claims.roles == []

    def test_from_jwt_payload_full(self):
        payload = {
            "sub": "user-456",
            "zoiko_tenant": "t-xyz",
            "email": "dev@zoikotech.com",
            "zoiko_roles": ["approver", "viewer"],
        }
        claims = ZoikoClaims.from_jwt_payload(payload)
        assert claims.email == "dev@zoikotech.com"
        assert claims.roles == ["approver", "viewer"]


class TestAssertTenantBinding:
    def test_matching_tenant_does_not_raise(self):
        claims = ZoikoClaims(sub="s", tenant_id="t-1", email=None, roles=[])
        assert_tenant_binding("t-1", claims)  # no exception

    def test_mismatched_tenant_raises(self):
        claims = ZoikoClaims(sub="s", tenant_id="t-1", email=None, roles=[])
        with pytest.raises(TenantMismatchError):
            assert_tenant_binding("t-2", claims)


# ---------------------------------------------------------------------------
# kafka/__init__.py
# ---------------------------------------------------------------------------


class TestKafka:
    def test_partition_key_format(self):
        assert partition_key("tenant-1", "case-abc") == "tenant-1:case-abc"

    def test_all_17_topics_defined(self):
        assert len(TOPICS) == 18  # 17 pipeline topics + security.event.detected (FR-024)

    def test_topic_names_have_version_suffix(self):
        for name, topic in TOPICS.items():
            assert topic.endswith(".v1"), f"Topic {name!r} missing .v1 suffix"

    def test_kafka_message_dataclass(self):
        msg = KafkaMessage(
            topic="zoiko.ingestion.source-record-created.v1",
            key="t1:c1",
            value=b"payload",
            headers={"x-correlation-id": "abc"},
        )
        assert msg.key == "t1:c1"


# ---------------------------------------------------------------------------
# idempotency/__init__.py  (mocked Redis)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotency_acquire_first_time():
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    store = IdempotencyStore(mock_redis)
    result = await store.acquire("tenant-1", "idem-key-1")
    assert result is True


@pytest.mark.asyncio
async def test_idempotency_acquire_already_exists():
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=None)
    store = IdempotencyStore(mock_redis)
    result = await store.acquire("tenant-1", "idem-key-1")
    assert result is False


@pytest.mark.asyncio
async def test_idempotency_status_none_when_missing():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    store = IdempotencyStore(mock_redis)
    result = await store.status("tenant-1", "missing")
    assert result is None


@pytest.mark.asyncio
async def test_idempotency_status_in_progress():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b"IN_PROGRESS")
    store = IdempotencyStore(mock_redis)
    result = await store.status("tenant-1", "key-1")
    assert result == IdempotencyStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_idempotency_complete():
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    store = IdempotencyStore(mock_redis)
    await store.complete("tenant-1", "key-1")
    mock_redis.set.assert_called_once()