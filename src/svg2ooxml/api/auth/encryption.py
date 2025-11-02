"""Token encryption/decryption utilities for secure storage."""
import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _get_encryption_key() -> bytes:
    """Get encryption key from environment/secret.

    Raises:
        ValueError: If TOKEN_ENCRYPTION_KEY not set
    """
    key_b64 = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key_b64:
        raise ValueError("TOKEN_ENCRYPTION_KEY environment variable not set")

    try:
        return base64.urlsafe_b64decode(key_b64)
    except Exception as e:
        raise ValueError(f"Invalid TOKEN_ENCRYPTION_KEY format: {e}")


def encrypt_token(token: str) -> str:
    """Encrypt OAuth token for secure storage.

    Args:
        token: OAuth token to encrypt

    Returns:
        Base64-encoded encrypted token

    Raises:
        ValueError: If encryption fails
    """
    try:
        fernet = Fernet(_get_encryption_key())
        encrypted = fernet.encrypt(token.encode('utf-8'))
        encrypted_b64 = base64.urlsafe_b64encode(encrypted).decode('utf-8')

        logger.debug("Token encrypted successfully")
        return encrypted_b64

    except Exception as e:
        logger.error(f"Token encryption failed: {e}")
        raise ValueError(f"Failed to encrypt token: {e}")


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt stored OAuth token.

    Args:
        encrypted_token: Base64-encoded encrypted token

    Returns:
        Decrypted OAuth token

    Raises:
        ValueError: If decryption fails
        InvalidToken: If token is corrupted or key is wrong
    """
    try:
        fernet = Fernet(_get_encryption_key())
        encrypted = base64.urlsafe_b64decode(encrypted_token)
        decrypted = fernet.decrypt(encrypted).decode('utf-8')

        logger.debug("Token decrypted successfully")
        return decrypted

    except InvalidToken:
        logger.error("Token decryption failed: invalid token or wrong key")
        raise
    except Exception as e:
        logger.error(f"Token decryption failed: {e}")
        raise ValueError(f"Failed to decrypt token: {e}")


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key.

    Returns:
        Base64-encoded encryption key (for TOKEN_ENCRYPTION_KEY env var)

    Usage:
        >>> key = generate_encryption_key()
        >>> print(f"TOKEN_ENCRYPTION_KEY={key}")
    """
    key = Fernet.generate_key()
    return base64.urlsafe_b64encode(key).decode('utf-8')
