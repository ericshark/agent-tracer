import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

_hasher = PasswordHasher()

API_KEY_PREFIX = "at_"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> str | None:
    """Return the user id encoded in a valid token, else None."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


def generate_api_key() -> tuple[str, str, str]:
    """Return (plaintext_key, sha256_hash, display_prefix)."""
    key = API_KEY_PREFIX + secrets.token_hex(24)
    return key, hash_api_key(key), key[:10]


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_share_token() -> str:
    return secrets.token_urlsafe(32)


def _fernet() -> Fernet:
    # Derive a stable 32-byte Fernet key from SECRET_KEY.
    digest = hashlib.sha256(get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return None


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "…" + value[-4:]
