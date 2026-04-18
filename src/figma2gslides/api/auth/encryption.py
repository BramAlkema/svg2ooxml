"""Token encryption helpers used by background export jobs."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


def _token_cipher() -> Fernet:
    key = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key:
        key = Fernet.generate_key().decode("utf-8")
        os.environ["TOKEN_ENCRYPTION_KEY"] = key
    return Fernet(key.encode("utf-8"))


def encrypt_token(token: str) -> str:
    return _token_cipher().encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(token: str) -> str:
    return _token_cipher().decrypt(token.encode("utf-8")).decode("utf-8")


__all__ = ["decrypt_token", "encrypt_token"]
