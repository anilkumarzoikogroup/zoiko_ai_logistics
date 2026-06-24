"""Tests for zoiko-kms key hierarchy and local backend."""
import pytest
from zoiko_kms.hierarchy import KeyHierarchy, KeyPurpose, KeyBackend
from zoiko_kms.local_backend import LocalKMSBackend


TENANT_ID = "tenant-abc-123"
SLUG      = "acme-logistics"


class TestKeyHierarchy:

    def setup_method(self):
        self.kms = KeyHierarchy(env="dev")

    def test_provision_creates_three_keys(self):
        keys = self.kms.provision_tenant(TENANT_ID, SLUG)
        assert len(keys) == 3
        purposes = {k.purpose for k in keys}
        assert purposes == {KeyPurpose.ROOT_CA, KeyPurpose.DEK_ENCRYPT, KeyPurpose.SIGNING}

    def test_all_dev_keys_use_software_backend(self):
        keys = self.kms.provision_tenant(TENANT_ID, SLUG)
        for k in keys:
            assert k.backend == KeyBackend.SOFTWARE

    def test_get_active_key_returns_signing_key(self):
        self.kms.provision_tenant(TENANT_ID, SLUG)
        k = self.kms.get_active_key(TENANT_ID, KeyPurpose.SIGNING)
        assert k is not None
        assert k.purpose == KeyPurpose.SIGNING
        assert k.is_active

    def test_rotate_key_increments_version(self):
        self.kms.provision_tenant(TENANT_ID, SLUG)
        old = self.kms.get_active_key(TENANT_ID, KeyPurpose.SIGNING)
        assert old.version == 1

        new = self.kms.rotate_key(TENANT_ID, KeyPurpose.SIGNING)
        assert new.version == 2
        assert new.is_active
        assert not old.is_active

    def test_rotate_makes_old_inactive(self):
        self.kms.provision_tenant(TENANT_ID, SLUG)
        self.kms.rotate_key(TENANT_ID, KeyPurpose.SIGNING)
        active = self.kms.get_active_key(TENANT_ID, KeyPurpose.SIGNING)
        assert active.version == 2

    def test_list_keys_returns_all_versions(self):
        self.kms.provision_tenant(TENANT_ID, SLUG)
        self.kms.rotate_key(TENANT_ID, KeyPurpose.DEK_ENCRYPT)
        keys = self.kms.list_keys(TENANT_ID)
        assert len(keys) == 4   # 3 original + 1 rotated

    def test_fingerprint_is_deterministic(self):
        self.kms.provision_tenant(TENANT_ID, SLUG)
        k = self.kms.get_active_key(TENANT_ID, KeyPurpose.SIGNING)
        assert k.fingerprint() == k.fingerprint()

    def test_prod_uses_hsm_backend(self):
        prod_kms = KeyHierarchy(env="prod")
        keys = prod_kms.provision_tenant(TENANT_ID, SLUG)
        for k in keys:
            assert k.backend == KeyBackend.HSM, f"{k.purpose} should use HSM in prod"

    def test_keys_needing_rotation_empty_initially(self):
        self.kms.provision_tenant(TENANT_ID, SLUG)
        # Freshly provisioned keys rotate in 90 days — none need rotation now
        assert self.kms.keys_needing_rotation() == []


class TestLocalKMSBackend:

    def setup_method(self):
        self.backend = LocalKMSBackend()

    def test_sign_returns_64_bytes(self):
        sig = self.backend.sign("dev/test-signing-v1", b"hello world")
        assert len(sig) == 64

    def test_verify_valid_signature(self):
        resource = "dev/test-key-v1"
        payload  = b"test payload"
        sig      = self.backend.sign(resource, payload)
        assert self.backend.verify(resource, payload, sig) is True

    def test_verify_wrong_payload_fails(self):
        resource = "dev/test-key-v1"
        sig      = self.backend.sign(resource, b"original")
        assert self.backend.verify(resource, b"tampered", sig) is False

    def test_verify_wrong_resource_fails(self):
        sig = self.backend.sign("dev/key-a", b"payload")
        assert self.backend.verify("dev/key-b", b"payload", sig) is False

    def test_encrypt_decrypt_roundtrip(self):
        resource   = "dev/dek-v1"
        plaintext  = b"sensitive invoice data"
        ciphertext = self.backend.encrypt(resource, plaintext)
        assert ciphertext != plaintext
        recovered  = self.backend.decrypt(resource, ciphertext)
        assert recovered == plaintext

    def test_same_seed_produces_same_keys(self):
        seed     = b"deterministic-seed-32-bytes-long!"
        b1       = LocalKMSBackend(master_seed=seed)
        b2       = LocalKMSBackend(master_seed=seed)
        resource = "dev/test-v1"
        payload  = b"same payload"
        sig1     = b1.sign(resource, payload)
        sig2     = b2.sign(resource, payload)
        assert sig1 == sig2

    def test_public_key_der_is_bytes(self):
        der = self.backend.public_key_der("dev/signing-v1")
        assert isinstance(der, bytes)
        assert len(der) > 0
