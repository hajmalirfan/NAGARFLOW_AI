import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: int) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "exp": expires_at},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def generate_reset_token() -> str:
    """Create a cryptographically secure, URL-safe reset token.

    ``token_urlsafe(32)`` draws 32 random bytes (256 bits) from the
    operating system's secure source, which is far beyond guessing range.
    """
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    """Hash a reset token for storage and lookup.

    A plain SHA-256 is correct here, unlike for passwords. The token is
    256 random bits rather than something a person chose, so there is no
    dictionary to attack and no need for a deliberately slow hash. A fast
    hash also keeps the column directly indexable.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
