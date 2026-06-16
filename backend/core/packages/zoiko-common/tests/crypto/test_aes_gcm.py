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
        ct, iv = encrypt(dek, plaintext)
        assert decrypt(dek, ct, iv=iv) == plaintext

    def test_ciphertext_not_equal_plaintext(self):
        encrypt, _, get_dek = self._mod()
        dek  = get_dek("tenant-test-2")
        pt   = b"test payload"
        ct, _ = encrypt(dek, pt)
        assert ct != pt

    def test_nonce_length_12_bytes(self):
        encrypt, _, get_dek = self._mod()
        dek = get_dek("tenant-test-3")
        ct, iv = encrypt(dek, b"hello")
        # nonce=12, ct(5) + tag(16) = 21
        assert len(iv) == 12
        assert len(ct) == 21

    def test_different_nonces_each_call(self):
        encrypt, _, get_dek = self._mod()
        dek = get_dek("tenant-test-4")
        ct1, iv1 = encrypt(dek, b"same plaintext")
        ct2, iv2 = encrypt(dek, b"same plaintext")
        # Different nonces → different ciphertexts
        assert iv1 != iv2

    def test_wrong_dek_raises_on_decrypt(self):
        encrypt, decrypt, get_dek = self._mod()
        dek1 = get_dek("tenant-a")
        dek2 = get_dek("tenant-b")
        ct, iv = encrypt(dek1, b"secret")
        with pytest.raises(ValueError):
            decrypt(dek2, ct, iv=iv)

    def test_tampered_ciphertext_raises(self):
        encrypt, decrypt, get_dek = self._mod()
        dek = get_dek("tenant-c")
        ct, iv = encrypt(dek, b"secret")
        ct  = bytearray(ct)
        ct[-1] ^= 0xFF   # flip last byte of tag
        with pytest.raises(ValueError):
            decrypt(dek, bytes(ct), iv=iv)

    def test_encrypt_with_aad(self):
        encrypt, decrypt, get_dek = self._mod()
        dek = get_dek("tenant-aad")
        pt  = b"payload with aad"
        aad = b"carrier_invoice|tenant-1|INV-001"
        ct, iv = encrypt(dek, pt, aad=aad)
        assert decrypt(dek, ct, iv=iv, aad=aad) == pt

    def test_decrypt_wrong_aad_raises(self):
        encrypt, decrypt, get_dek = self._mod()
        dek  = get_dek("tenant-aad2")
        pt   = b"sensitive data"
        aad1 = b"correct-aad"
        aad2 = b"wrong-aad"
        ct, iv = encrypt(dek, pt, aad=aad1)
        with pytest.raises(ValueError):
            decrypt(dek, ct, iv=iv, aad=aad2)

    def test_dek_is_32_bytes(self):
        _, _, get_dek = self._mod()
        assert len(get_dek("any-tenant")) == 32

    def test_deterministic_dek_per_tenant(self):
        _, _, get_dek = self._mod()
        assert get_dek("t1") == get_dek("t1")
        assert get_dek("t1") != get_dek("t2")
