from collections.abc import Callable, Generator

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import PERMISSIONS
from app.db.session import SessionLocal
from app.evaluation import CATALOG_CODE_PREFIX
from app.models.user import User

bearer_scheme = HTTPBearer()


def reject_reserved_code(code: str, current: str | None = None) -> None:
    """Refuse a catalogue code, unless the record already has it."""
    if code.upper().startswith(CATALOG_CODE_PREFIX) and code != current:
        raise HTTPException(
            status_code=422, detail=f"Codes starting {CATALOG_CODE_PREFIX} are reserved."
        )


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found.")
    return user


def require(name: str) -> Callable[..., User]:
    """The signed-in user, if their role has this permission.

    The role comes from the database on each request, so a change applies at
    once. A test walks every route and reads ``.permission`` to prove each
    one declares a permission.
    """
    allowed = PERMISSIONS[name]

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account does not have access to this.",
            )
        return user

    dependency.permission = name
    return dependency


def commit_or_conflict(db: Session, detail: str) -> None:
    """Save, turning a unique constraint failure into a 409.

    The check before saving can pass for two requests at once, so the
    database constraint has the last word.
    """
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from None
