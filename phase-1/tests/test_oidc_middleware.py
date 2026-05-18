"""Tests for OIDC JWT claims and token verifier."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import pytest
from middleware.oidc.claims import ZoikoClaims, TenantContext
from middleware.oidc.token_verifier import TokenVerifier, TokenExpiredError, TokenInvalidError

DEV_SECRET = b"zoiko-dev-secret-for-testing-only"
TENANT_ID  = "tenant-abc-123"
SUB        = "analyst@zoikotech.com"


@pytest.fixture
def verifier():
    return TokenVerifier(
        dev_secret = DEV_SECRET,
        issuer     = "https://auth.zoikotech.com",
    )


class TestZoikoClaims:

    def _make_claims(self, **kwargs):
        defaults = {
            "sub":       SUB,
            "iss":       "https://auth.zoikotech.com",
            "aud":       "zoiko-dev",
            "exp":       int(time.time()) + 3600,
            "iat":       int(time.time()),
            "tenant_id": TENANT_ID,
            "roles":     ["analyst"],
        }
        defaults.update(kwargs)
        return ZoikoClaims.from_dict(defaults)

    def test_from_dict_valid(self):
        c = self._make_claims()
        assert c.sub == SUB
        assert c.tenant_id == TENANT_ID
        assert c.is_analyst

    def test_is_not_expired(self):
        c = self._make_claims(exp=int(time.time()) + 3600)
        assert not c.is_expired

    def test_is_expired(self):
        c = self._make_claims(exp=int(time.time()) - 1)
        assert c.is_expired

    def test_role_checks(self):
        analyst = self._make_claims(roles=["analyst"])
        manager = self._make_claims(roles=["manager"])
        admin   = self._make_claims(roles=["admin", "manager"])

        assert analyst.is_analyst and not analyst.is_manager
        assert manager.is_manager and not manager.is_analyst
        assert admin.is_admin and admin.is_manager

    def test_missing_required_claim_raises(self):
        with pytest.raises(ValueError, match="missing required claims"):
            ZoikoClaims.from_dict({"sub": "x"})


class TestTokenVerifier:

    def test_make_and_verify_dev_token(self, verifier):
        token  = verifier.make_dev_token(sub=SUB, tenant_id=TENANT_ID, roles=["analyst"])
        claims = verifier.verify(token, expected_audience="zoiko-dev")
        assert claims.sub == SUB
        assert claims.tenant_id == TENANT_ID
        assert "analyst" in claims.roles

    def test_expired_token_raises(self, verifier):
        token = verifier.make_dev_token(sub=SUB, tenant_id=TENANT_ID, ttl_sec=-1)
        with pytest.raises(TokenExpiredError):
            verifier.verify(token)

    def test_tampered_token_raises(self, verifier):
        token  = verifier.make_dev_token(sub=SUB, tenant_id=TENANT_ID)
        parts  = token.split(".")
        parts[1] = parts[1][:-2] + "XX"   # corrupt payload
        with pytest.raises((TokenInvalidError, Exception)):
            verifier.verify(".".join(parts))

    def test_wrong_audience_raises(self, verifier):
        token = verifier.make_dev_token(sub=SUB, tenant_id=TENANT_ID, audience="service-a")
        with pytest.raises(TokenInvalidError, match="Audience mismatch"):
            verifier.verify(token, expected_audience="service-b")

    def test_malformed_token_raises(self, verifier):
        with pytest.raises(TokenInvalidError):
            verifier.verify("not.a.valid.jwt.token.at.all")

    def test_manager_role_in_token(self, verifier):
        token  = verifier.make_dev_token(sub="mgr@zoikotech.com", tenant_id=TENANT_ID, roles=["manager"])
        claims = verifier.verify(token)
        assert claims.is_manager
        assert not claims.is_analyst
