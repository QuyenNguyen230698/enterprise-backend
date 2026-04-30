import base64
import hashlib
from app.core.config import settings


def _get_fernet():
    from cryptography.fernet import Fernet
    key = settings.ENCRYPTION_KEY
    if not key:
        # Derive a stable key from a fallback secret so service still starts
        raw = hashlib.sha256(b"enterprise-meeting-fallback-key").digest()
        key = base64.urlsafe_b64encode(raw).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Encrypt a string, returns URL-safe base64 ciphertext."""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext string."""
    if not ciphertext:
        return ""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
