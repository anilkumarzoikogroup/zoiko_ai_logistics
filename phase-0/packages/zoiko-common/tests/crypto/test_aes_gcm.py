"""AES-256-GCM tests — no DB, no I/O."""
import pytest


class TestAESGCM:
    def _mod(self):
        from zoiko_common.crypto.aes_gcm import encrypt, decrypt, get_dek
        return encrypt, decrypt, get_dek

    def test_encrypt_decrypt_roundtrip(self):
        encrypt, decrypt, get_dek = self._mod()
        dek = get_dek("tenant-test-1")
        plaintext = b"BlueDart invoice canonical bytes"
        ct = encrypt(dek, plaintext)
        assert decrypt(dek, ct) == plaintext

    def test_ciphertext_not_equal_plaintext(self):
        encrypt, _, get_dek = self._mod()
        dek  = get_dek("tenant-test-2")
        pt   = b"test payload"
        ct   = encrypt(dek, pt)
        assert ct != pt

    def test_nonce_prefix_12_bytes(self):
        encrypt, _, get_dek = self._mod()
        dek = get_dek("tenant-test-3")
        ct  = encrypt(dek, b"hello")
        # nonce(12) + ct(5) + tag(16) = 33
        assert len(ct) == 33

    def test_different_nonces_each_call(self):
        encrypt, _, get_dek = self._mod()
        dek = get_dek("tenant-test-4")
        ct1 = encrypt(dek, b"same plaintext")
        ct2 = encrypt(dek, b"same plaintext")
        # Different nonces → different ciphertexts
        assert ct1[:12] != ct2[:12]

    def test_wrong_dek_raises_on_decrypt(self):
        encrypt, decrypt, get_dek = self._mod()
        dek1 = get_dek("tenant-a")
        dek2 = get_dek("tenant-b")
        ct   = encrypt(dek1, b"secret")
        with pytest.raises(ValueError):
            decrypt(dek2, ct)

    def test_tampered_ciphertext_raises(self):
        encrypt, decrypt, get_dek = self._mod()
        dek = get_dek("tenant-c")
        ct  = bytearray(encrypt(dek, b"secret"))
        ct[-1] ^= 0xFF   # flip last byte of tag
        with pytest.raises(ValueError):
            decrypt(dek, bytes(ct))

    def test_dek_is_32_bytes(self):
        _, _, get_dek = self._mod()
        assert len(get_dek("any-tenant")) == 32

    def test_deterministic_dek_per_tenant(self):
        _, _, get_dek = self._mod()
        assert get_dek("t1") == get_dek("t1")
        assert get_dek("t1") != get_dek("t2")
