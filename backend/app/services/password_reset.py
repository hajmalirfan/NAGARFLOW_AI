"""Password reset business logic.

The rules enforced here are the ones that make the feature safe:

* the raw token is generated with a secure random source and never stored
* a token lives for ``reset_token_expire_minutes`` (15) and no longer
* a token works exactly once
* a successful reset invalidates every other outstanding token
* nothing in the response tells the caller whether an email is registered
"""

import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.core.security import generate_reset_token, hash_password, hash_reset_token
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services import email as email_service

logger = logging.getLogger(__name__)

RESET_SUBJECT = "Reset your NagarFlow password"


class InvalidResetToken(Exception):
    """Raised when a token is unknown, expired, or already used."""


def _build_reset_link(raw_token: str) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={raw_token}"


def _build_reset_email(user: User, raw_token: str) -> str:
    minutes = settings.reset_token_expire_minutes
    return (
        f"Hello {user.name},\n\n"
        "We received a request to reset the password for your NagarFlow "
        "account. Open the link below to choose a new password:\n\n"
        f"{_build_reset_link(raw_token)}\n\n"
        f"This link expires in {minutes} minutes and can be used once.\n\n"
        "If you did not request a password reset you can ignore this "
        "email. Your password will not change until you open the link and "
        "choose a new one.\n\n"
        "NagarFlow"
    )


def request_password_reset(db: Session, raw_email: str) -> None:
    """Issue a reset token and email it, if the address has an account.

    Returns nothing in every case. The caller must send the same response
    whether or not an account was found, so that this endpoint cannot be
    used to discover which email addresses are registered.
    """
    normalized_email = raw_email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))

    if user is None:
        logger.info("Password reset requested for an address with no account")
        return

    raw_token = generate_reset_token()
    issued_at = utcnow()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_reset_token(raw_token),
            created_at=issued_at,
            expires_at=issued_at + timedelta(minutes=settings.reset_token_expire_minutes),
        )
    )
    db.commit()

    email_service.send_email(
        to=user.email,
        subject=RESET_SUBJECT,
        body=_build_reset_email(user, raw_token),
    )


def resolve_usable_token(db: Session, raw_token: str) -> tuple[PasswordResetToken, User]:
    """Look up a token that is known, unexpired, and unused.

    Raises ``InvalidResetToken`` for every failure, so the caller cannot
    distinguish an unknown token from an expired or spent one.
    """
    token_row = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_reset_token(raw_token)
        )
    )
    if token_row is None or not token_row.is_usable(utcnow()):
        raise InvalidResetToken

    user = db.get(User, token_row.user_id)
    if user is None:
        raise InvalidResetToken

    return token_row, user


def reset_password(db: Session, raw_token: str, new_password: str) -> User:
    """Set a new password and spend every outstanding token for the user."""
    _token_row, user = resolve_usable_token(db, raw_token)

    spent_at = utcnow()
    user.hashed_password = hash_password(new_password)
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=spent_at)
    )
    db.commit()
    db.refresh(user)

    logger.info("Password reset completed for user id %s", user.id)
    return user
