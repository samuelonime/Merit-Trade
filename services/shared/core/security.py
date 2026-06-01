"""
Security utilities for Merit-Trade AI.
Handles AES-256-GCM encryption for sensitive credentials,
bcrypt password hashing, and key derivation.
"""
import base64
import os
from typing import Union

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from passlib.context import CryptContext

from .config import settings

# Password hashing with bcrypt (cost factor 12)
_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(plain: str) -> str:
    """Hash a password using bcrypt."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return _pwd_context.verify(plain, hashed)


def _get_aes_key() -> bytes:
    """Derive 32-byte AES key from config."""
    key_str = settings.AES_ENCRYPTION_KEY
    # Decode from base64 if base64-encoded, else use raw bytes
    try:
        key = base64.b64decode(key_str)
    except Exception:
        key = key_str.encode("utf-8")
    if len(key) < 32:
        raise ValueError("AES_ENCRYPTION_KEY must be at least 32 bytes")
    return key[:32]


def encrypt_value(plaintext: Union[str, bytes]) -> bytes:
    """
    Encrypt a value using AES-256-GCM.
    Returns: nonce (12 bytes) + ciphertext + tag, as bytes.
    This is stored as BYTEA in PostgreSQL.
    """
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")

    key = _get_aes_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext  # nonce prepended for decryption


def decrypt_value(encrypted: bytes) -> str:
    """
    Decrypt an AES-256-GCM encrypted value.
    Expects nonce (12 bytes) prepended to ciphertext.
    """
    if len(encrypted) < 13:
        raise ValueError("Invalid encrypted data: too short")

    key = _get_aes_key()
    aesgcm = AESGCM(key)
    nonce = encrypted[:12]
    ciphertext = encrypted[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def mask_credential(value: str, visible: int = 4) -> str:
    """Mask a credential for display/logging. Shows last N chars."""
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]
