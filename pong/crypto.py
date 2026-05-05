"""Primitivas criptograficas para PongIA P2P.

X25519 key agreement + XChaCha20-Poly1305 AEAD + Ed25519 signatures.
Todas las funciones son puras (sin estado) y wrappean PyNaCl / libsodium.
"""

from __future__ import annotations

from nacl.bindings import (
    crypto_aead_xchacha20poly1305_ietf_ABYTES,
    crypto_aead_xchacha20poly1305_ietf_KEYBYTES,
    crypto_aead_xchacha20poly1305_ietf_NPUBBYTES,
    crypto_aead_xchacha20poly1305_ietf_decrypt,
    crypto_aead_xchacha20poly1305_ietf_encrypt,
    crypto_scalarmult,
)
from nacl.exceptions import CryptoError
from nacl.hash import blake2b
from nacl.public import PrivateKey
from nacl.utils import random

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

AEAD_KEY_BYTES: int = crypto_aead_xchacha20poly1305_ietf_KEYBYTES  # 32
AEAD_NONCE_BYTES: int = crypto_aead_xchacha20poly1305_ietf_NPUBBYTES  # 24
AEAD_TAG_BYTES: int = crypto_aead_xchacha20poly1305_ietf_ABYTES  # 16
X25519_KEY_BYTES: int = 32

# ---------------------------------------------------------------------------
# X25519 key exchange
# ---------------------------------------------------------------------------


def generate_ephemeral_x25519() -> tuple[bytes, bytes]:
    """Genera par efimero X25519.

    Returns:
        (private_key, public_key) — ambos de 32 bytes.
    """
    sk = PrivateKey.generate()
    return bytes(sk), bytes(sk.public_key)


def ecdh(my_private: bytes, peer_public: bytes) -> bytes:
    """X25519 scalar multiplication → 32-byte shared secret."""
    result: bytes = crypto_scalarmult(my_private, peer_public)
    return result


# ---------------------------------------------------------------------------
# KDF (Blake2b)
# ---------------------------------------------------------------------------


def derive_key(
    ikm: bytes,
    salt: bytes = b"",
    context: bytes = b"",
) -> bytes:
    """Deriva una clave de 32 bytes via Blake2b keyed hash.

    Args:
        ikm: Input key material (shared secret o concatenacion de ECDH).
        salt: Sal fija por protocolo (ej. b"pongia-hs-4.0").
        context: Info adicional (ej. b"session" o b"handshake").

    Returns:
        32 bytes derivados.
    """
    from nacl.encoding import RawEncoder

    result: bytes = blake2b(
        salt + context,
        digest_size=AEAD_KEY_BYTES,
        key=ikm,
        encoder=RawEncoder,
    )
    return result


# ---------------------------------------------------------------------------
# AEAD — XChaCha20-Poly1305
# ---------------------------------------------------------------------------


def aead_encrypt(
    key: bytes,
    plaintext: bytes,
    aad: bytes = b"",
) -> bytes:
    """Cifra con XChaCha20-Poly1305.

    Returns:
        nonce (24 B) || ciphertext+tag — listo para enviar.
    """
    nonce: bytes = random(AEAD_NONCE_BYTES)
    ct: bytes = crypto_aead_xchacha20poly1305_ietf_encrypt(
        plaintext, aad, nonce, key,
    )
    return nonce + ct


def aead_decrypt(
    key: bytes,
    nonce_ct: bytes,
    aad: bytes = b"",
) -> bytes:
    """Descifra XChaCha20-Poly1305.

    Args:
        nonce_ct: nonce (24 B) || ciphertext+tag (como devuelve aead_encrypt).

    Raises:
        CryptoError: si la autenticacion falla (datos alterados).
    """
    if len(nonce_ct) < AEAD_NONCE_BYTES + AEAD_TAG_BYTES:
        raise CryptoError("Mensaje demasiado corto para XChaCha20-Poly1305")
    nonce = nonce_ct[:AEAD_NONCE_BYTES]
    ct = nonce_ct[AEAD_NONCE_BYTES:]
    result: bytes = crypto_aead_xchacha20poly1305_ietf_decrypt(ct, aad, nonce, key)
    return result


# ---------------------------------------------------------------------------
# Cifrado en disco (at-rest)
# ---------------------------------------------------------------------------


def encrypt_at_rest(machine_key: bytes, data: bytes) -> bytes:
    """Cifra datos para almacenamiento local.

    Usa una clave derivada del hardware (machine_key) para que los datos
    solo sean legibles en la misma maquina.

    Returns:
        nonce (24 B) || ciphertext+tag.
    """
    enc_key = derive_key(machine_key, salt=b"pongia-at-rest-4.0")
    return aead_encrypt(enc_key, data)


def decrypt_at_rest(machine_key: bytes, blob: bytes) -> bytes:
    """Descifra datos almacenados localmente.

    Raises:
        CryptoError: si machine_key es diferente o datos alterados.
    """
    enc_key = derive_key(machine_key, salt=b"pongia-at-rest-4.0")
    return aead_decrypt(enc_key, blob)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


# _RawEncoder eliminado: usamos nacl.encoding.RawEncoder directamente para
# que blake2b lo acepte sin problemas de tipos.
