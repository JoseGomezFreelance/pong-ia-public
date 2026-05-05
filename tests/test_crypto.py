"""Tests para pong.crypto — primitivas XChaCha20-Poly1305 + X25519."""

from __future__ import annotations

import pytest
from nacl.exceptions import CryptoError

from pong.crypto import (
    AEAD_KEY_BYTES,
    AEAD_NONCE_BYTES,
    AEAD_TAG_BYTES,
    X25519_KEY_BYTES,
    aead_decrypt,
    aead_encrypt,
    decrypt_at_rest,
    derive_key,
    ecdh,
    encrypt_at_rest,
    generate_ephemeral_x25519,
)


# ---------------------------------------------------------------------------
# X25519 key exchange
# ---------------------------------------------------------------------------


class TestX25519:
    def test_key_sizes(self) -> None:
        sk, pk = generate_ephemeral_x25519()
        assert len(sk) == X25519_KEY_BYTES
        assert len(pk) == X25519_KEY_BYTES

    def test_keys_are_different(self) -> None:
        sk, pk = generate_ephemeral_x25519()
        assert sk != pk

    def test_each_call_generates_unique_keys(self) -> None:
        sk1, pk1 = generate_ephemeral_x25519()
        sk2, pk2 = generate_ephemeral_x25519()
        assert sk1 != sk2
        assert pk1 != pk2


class TestECDH:
    def test_shared_secret_is_symmetric(self) -> None:
        sk_a, pk_a = generate_ephemeral_x25519()
        sk_b, pk_b = generate_ephemeral_x25519()
        assert ecdh(sk_a, pk_b) == ecdh(sk_b, pk_a)

    def test_shared_secret_is_32_bytes(self) -> None:
        sk_a, pk_a = generate_ephemeral_x25519()
        sk_b, pk_b = generate_ephemeral_x25519()
        shared = ecdh(sk_a, pk_b)
        assert len(shared) == 32

    def test_different_peers_yield_different_secrets(self) -> None:
        sk_a, pk_a = generate_ephemeral_x25519()
        _, pk_b = generate_ephemeral_x25519()
        _, pk_c = generate_ephemeral_x25519()
        assert ecdh(sk_a, pk_b) != ecdh(sk_a, pk_c)


# ---------------------------------------------------------------------------
# KDF
# ---------------------------------------------------------------------------


class TestDeriveKey:
    def test_output_length(self) -> None:
        key = derive_key(b"x" * 32, salt=b"s", context=b"c")
        assert len(key) == AEAD_KEY_BYTES

    def test_deterministic(self) -> None:
        ikm = b"shared_secret_32_bytes__________"
        k1 = derive_key(ikm, salt=b"salt", context=b"ctx")
        k2 = derive_key(ikm, salt=b"salt", context=b"ctx")
        assert k1 == k2

    def test_different_salt_different_key(self) -> None:
        ikm = b"shared_secret_32_bytes__________"
        k1 = derive_key(ikm, salt=b"salt-a")
        k2 = derive_key(ikm, salt=b"salt-b")
        assert k1 != k2

    def test_different_context_different_key(self) -> None:
        ikm = b"shared_secret_32_bytes__________"
        k1 = derive_key(ikm, context=b"handshake")
        k2 = derive_key(ikm, context=b"session")
        assert k1 != k2


# ---------------------------------------------------------------------------
# AEAD — XChaCha20-Poly1305
# ---------------------------------------------------------------------------


class TestAEAD:
    def setup_method(self) -> None:
        self.key = derive_key(b"test_key_material_______________")

    def test_round_trip(self) -> None:
        pt = b"hello world"
        ct = aead_encrypt(self.key, pt)
        assert aead_decrypt(self.key, ct) == pt

    def test_round_trip_with_aad(self) -> None:
        pt = b"payload"
        aad = b"protocol-version-4.0"
        ct = aead_encrypt(self.key, pt, aad=aad)
        assert aead_decrypt(self.key, ct, aad=aad) == pt

    def test_wrong_aad_fails(self) -> None:
        ct = aead_encrypt(self.key, b"data", aad=b"correct")
        with pytest.raises(CryptoError):
            aead_decrypt(self.key, ct, aad=b"wrong")

    def test_wrong_key_fails(self) -> None:
        ct = aead_encrypt(self.key, b"data")
        wrong_key = derive_key(b"wrong_key_material______________")
        with pytest.raises(CryptoError):
            aead_decrypt(wrong_key, ct)

    def test_tampered_ciphertext_fails(self) -> None:
        ct = aead_encrypt(self.key, b"data")
        # Flip a byte in the ciphertext portion (after nonce)
        pos = AEAD_NONCE_BYTES + 2
        tampered = ct[:pos] + bytes([ct[pos] ^ 0xFF]) + ct[pos + 1 :]
        with pytest.raises(CryptoError):
            aead_decrypt(self.key, tampered)

    def test_tampered_nonce_fails(self) -> None:
        ct = aead_encrypt(self.key, b"data")
        tampered = bytes([ct[0] ^ 0xFF]) + ct[1:]
        with pytest.raises(CryptoError):
            aead_decrypt(self.key, tampered)

    def test_truncated_message_fails(self) -> None:
        ct = aead_encrypt(self.key, b"data")
        with pytest.raises(CryptoError):
            aead_decrypt(self.key, ct[:AEAD_NONCE_BYTES + 1])

    def test_empty_message_fails(self) -> None:
        with pytest.raises(CryptoError):
            aead_decrypt(self.key, b"")

    def test_output_format(self) -> None:
        pt = b"test"
        ct = aead_encrypt(self.key, pt)
        assert len(ct) == AEAD_NONCE_BYTES + len(pt) + AEAD_TAG_BYTES

    def test_nonce_is_random(self) -> None:
        ct1 = aead_encrypt(self.key, b"same")
        ct2 = aead_encrypt(self.key, b"same")
        # Nonces (first 24 bytes) should differ
        assert ct1[:AEAD_NONCE_BYTES] != ct2[:AEAD_NONCE_BYTES]
        # Ciphertexts should also differ due to different nonces
        assert ct1 != ct2

    def test_empty_plaintext(self) -> None:
        ct = aead_encrypt(self.key, b"")
        assert aead_decrypt(self.key, ct) == b""


# ---------------------------------------------------------------------------
# At-rest encryption
# ---------------------------------------------------------------------------


class TestAtRest:
    def setup_method(self) -> None:
        self.machine_key = b"hardware_derived_key_32_bytes____"

    def test_round_trip(self) -> None:
        data = b'{"signing_key": "abc123..."}'
        blob = encrypt_at_rest(self.machine_key, data)
        assert decrypt_at_rest(self.machine_key, blob) == data

    def test_wrong_machine_key_fails(self) -> None:
        blob = encrypt_at_rest(self.machine_key, b"secret")
        other_key = b"another_machine_key_32_bytes_____"
        with pytest.raises(CryptoError):
            decrypt_at_rest(other_key, blob)

    def test_tampered_blob_fails(self) -> None:
        blob = encrypt_at_rest(self.machine_key, b"secret")
        tampered = blob[:-1] + bytes([blob[-1] ^ 0xFF])
        with pytest.raises(CryptoError):
            decrypt_at_rest(self.machine_key, tampered)

    def test_different_encryptions_differ(self) -> None:
        data = b"same data"
        b1 = encrypt_at_rest(self.machine_key, data)
        b2 = encrypt_at_rest(self.machine_key, data)
        assert b1 != b2  # different nonces

    def test_empty_data(self) -> None:
        blob = encrypt_at_rest(self.machine_key, b"")
        assert decrypt_at_rest(self.machine_key, blob) == b""
