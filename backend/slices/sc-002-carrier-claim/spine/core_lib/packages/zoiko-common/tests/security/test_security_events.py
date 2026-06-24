"""Tests for security event publishing (FR-024)."""
import time
import pytest
from unittest.mock import MagicMock, patch

from zoiko_common.security.events import SecurityEventPublisher, SecurityEventKind


class _CaptureBroker:
    """In-memory broker that records sent messages."""
    def __init__(self):
        self.messages = []

    def send(self, topic, key, value, headers):
        self.messages.append({"topic": topic, "key": key, "value": value, "headers": headers})


class TestSecurityEventPublisher:
    """Tests call _send directly to avoid thread timing in CI."""

    def test_publish_cross_tenant_fires_message(self):
        import uuid
        broker = _CaptureBroker()
        pub = SecurityEventPublisher(broker=broker)
        event_id = str(uuid.uuid4())
        payload = {"event_id": event_id, "kind": "CROSS_TENANT_ACCESS",
                   "tenant_id": "aaaa-1111", "correlation_id": None,
                   "details": {"actor_sub": "user-x"}}
        pub._send("aaaa-1111", event_id, payload)
        assert len(broker.messages) == 1
        assert broker.messages[0]["topic"] == "zoiko.security.event-detected.v1"

    def test_publish_token_replay_fires_message(self):
        import uuid, json
        broker = _CaptureBroker()
        pub = SecurityEventPublisher(broker=broker)
        event_id = str(uuid.uuid4())
        payload = {"event_id": event_id, "kind": "TOKEN_REPLAY",
                   "tenant_id": "tenant-abc", "correlation_id": None,
                   "details": {"token_id": "tok-123"}}
        pub._send("tenant-abc", event_id, payload)
        assert len(broker.messages) == 1
        body = json.loads(broker.messages[0]["value"])
        assert body["payload"]["kind"] == "TOKEN_REPLAY"

    def test_publish_sod_violation_fires_message(self):
        import uuid, json
        broker = _CaptureBroker()
        pub = SecurityEventPublisher(broker=broker)
        event_id = str(uuid.uuid4())
        payload = {"event_id": event_id, "kind": "FORBIDDEN_FSM_TRANSITION",
                   "tenant_id": "tenant-xyz", "correlation_id": None,
                   "details": {"violation": "SOD_VIOLATION", "actor_sub": "proposer"}}
        pub._send("tenant-xyz", event_id, payload)
        assert len(broker.messages) == 1
        body = json.loads(broker.messages[0]["value"])
        assert body["payload"]["details"]["violation"] == "SOD_VIOLATION"

    def test_publish_never_raises_on_broker_failure(self):
        """Security events must never fail the request path."""
        import uuid
        bad_broker = MagicMock()
        bad_broker.send.side_effect = RuntimeError("Kafka unavailable")
        pub = SecurityEventPublisher(broker=bad_broker)
        event_id = str(uuid.uuid4())
        payload = {"event_id": event_id, "kind": "TOKEN_REPLAY",
                   "tenant_id": "t1", "correlation_id": None, "details": {}}
        # _send catches and logs — must not raise
        pub._send("t1", event_id, payload)

    def test_envelope_tenant_id_matches(self):
        import uuid, json
        broker = _CaptureBroker()
        pub = SecurityEventPublisher(broker=broker)
        event_id = str(uuid.uuid4())
        payload = {"event_id": event_id, "kind": "CROSS_TENANT_ACCESS",
                   "tenant_id": "tenant-42", "correlation_id": None, "details": {}}
        pub._send("tenant-42", event_id, payload)
        body = json.loads(broker.messages[0]["value"])
        assert body["tenant_id"] == "tenant-42"


class TestMtlsDependency:

    def test_dev_mode_always_passes(self):
        import os
        with patch.dict(os.environ, {"ZOIKO_MTLS_ENABLED": "false"}):
            # Re-import to pick up env var
            import importlib
            import zoiko_common.middleware.mtls as mtls_mod
            importlib.reload(mtls_mod)
            result = mtls_mod.require_mtls(x_forwarded_client_cert=None)
            assert result == "spiffe://zoiko.internal/service/dev"

    def test_extract_spiffe_uri(self):
        from zoiko_common.middleware.mtls import _extract_spiffe_uri
        xfcc = 'Hash=abc123;URI=spiffe://zoiko.internal/service/phase2;Subject="CN=phase2"'
        uri = _extract_spiffe_uri(xfcc)
        assert uri == "spiffe://zoiko.internal/service/phase2"

    def test_extract_spiffe_uri_missing(self):
        from zoiko_common.middleware.mtls import _extract_spiffe_uri
        assert _extract_spiffe_uri("Hash=abc123;Subject=foo") is None


class TestFeatureFlags:

    def test_unknown_flag_allowed_in_dev(self):
        import os
        from zoiko_common.middleware import feature_flags as ff
        with patch.dict(os.environ, {"ZOIKO_DEV_MODE": "true"}):
            assert ff.is_enabled("NONEXISTENT_FLAG", "tenant-1") is True

    def test_unknown_flag_denied_in_prod(self):
        import os
        from zoiko_common.middleware import feature_flags as ff
        with patch.dict(os.environ, {"ZOIKO_DEV_MODE": "false"}):
            assert ff.is_enabled("NONEXISTENT_FLAG_PROD", "tenant-1") is False

    def test_register_and_check_flag(self):
        from zoiko_common.middleware import feature_flags as ff
        ff.register_flag("SC_001_TEST", ["tenant-aaa", "tenant-bbb"])
        assert ff.is_enabled("SC_001_TEST", "tenant-aaa") is True
        assert ff.is_enabled("SC_001_TEST", "tenant-ccc") is False

    def test_wildcard_flag_allows_all(self):
        from zoiko_common.middleware import feature_flags as ff
        ff.register_flag("OPEN_FLAG", ["*"])
        assert ff.is_enabled("OPEN_FLAG", "any-tenant") is True

    def test_env_var_flag_loading(self):
        import os
        import importlib
        with patch.dict(os.environ, {"ZOIKO_FF_SC_001_ENABLED": "tenant-abc,tenant-xyz"}):
            import zoiko_common.middleware.feature_flags as ff_mod
            importlib.reload(ff_mod)
            assert ff_mod.is_enabled("SC_001_ENABLED", "tenant-abc") is True
            assert ff_mod.is_enabled("SC_001_ENABLED", "tenant-other") is False
