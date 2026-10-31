from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()
# Verified when the user does not exist, so login timing does not reveal valid emails.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_token(user_id: int, role: str, kind: str) -> str:
    settings = get_settings()
    ttl = (
        timedelta(minutes=settings.jwt_access_ttl_minutes)
        if kind == "access"
        else timedelta(days=settings.jwt_refresh_ttl_days)
    )
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "role": role, "type": kind, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_token(token: str, kind: str) -> dict:
    """Raises jwt.InvalidTokenError on bad signature, expiry or wrong token type."""
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGORITHM])
    if payload.get("type") != kind:
        raise jwt.InvalidTokenError("wrong token type")
    return payload
