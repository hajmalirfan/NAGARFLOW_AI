import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    UserCreate,
    UserLogin,
    UserResponse,
    VerifyResetTokenRequest,
    VerifyResetTokenResponse,
)
from app.services import password_reset as password_reset_service
from app.services.password_reset import InvalidResetToken

router = APIRouter(prefix="/auth", tags=["authentication"])
bearer_scheme = HTTPBearer()

# Shown for an unknown, expired, or already used reset link. It is
# deliberately the same message in all three cases.
INVALID_TOKEN_MESSAGE = (
    "This password reset link is invalid or has expired. Request a new one."
)


def issue_auth_response(user: User) -> AuthResponse:
    return AuthResponse(access_token=create_access_token(user.id), user=user)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> AuthResponse:
    email = str(payload.email).lower()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    user = User(name=payload.name.strip(), email=email, hashed_password=hash_password(payload.password))
    if not user.name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Please enter your name.")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.") from None
    db.refresh(user)
    return issue_auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> AuthResponse:
    email = str(payload.email).lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return issue_auth_response(user)


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


@router.get("/me", response_model=UserResponse)
def read_current_user(user: User = Depends(get_current_user)) -> User:
    return user


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def forgot_password(
    payload: ForgotPasswordRequest, db: Session = Depends(get_db)
) -> MessageResponse:
    """Start a password reset.

    Always returns the same 202 response. Telling the caller whether the
    address has an account would turn this endpoint into a way to harvest
    registered email addresses.
    """
    password_reset_service.request_password_reset(db, str(payload.email))
    return MessageResponse(
        message=(
            "If an account exists for that email address, a password reset "
            "link is on its way. Check your inbox."
        )
    )


@router.post("/verify-reset-token", response_model=VerifyResetTokenResponse)
def verify_reset_token(
    payload: VerifyResetTokenRequest, db: Session = Depends(get_db)
) -> VerifyResetTokenResponse:
    """Check a reset link before showing the new-password form."""
    try:
        _token_row, user = password_reset_service.resolve_usable_token(db, payload.token)
    except InvalidResetToken:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_TOKEN_MESSAGE
        ) from None
    return VerifyResetTokenResponse(valid=True, email=user.email)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    payload: ResetPasswordRequest, db: Session = Depends(get_db)
) -> MessageResponse:
    """Set a new password using a valid reset token."""
    try:
        password_reset_service.reset_password(db, payload.token, payload.password)
    except InvalidResetToken:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_TOKEN_MESSAGE
        ) from None
    return MessageResponse(
        message="Your password has been updated. You can now sign in."
    )
