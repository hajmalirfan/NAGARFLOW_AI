from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require
from app.core.rate_limit import RateLimiter, forgot_password_limiter, login_limiter
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

# Shown for an unknown, expired, or already used reset link. It is
# deliberately the same message in all three cases.
INVALID_TOKEN_MESSAGE = (
    "This password reset link is invalid or has expired. Request a new one."
)


def limit_keys(request: Request, email: str) -> tuple[str, str]:
    address = request.client.host if request.client else "unknown"
    return f"email:{email}", f"ip:{address}"


def refuse_if_limited(limiter: RateLimiter, keys: tuple[str, str]) -> None:
    if any(limiter.is_blocked(key) for key in keys):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
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
def login(
    payload: UserLogin, request: Request, db: Session = Depends(get_db)
) -> AuthResponse:
    email = str(payload.email).lower()
    keys = limit_keys(request, email)
    # Checked first, so a limited caller cannot learn a password is right.
    refuse_if_limited(login_limiter, keys)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        for key in keys:
            login_limiter.record(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_limiter.clear(keys[0])
    return issue_auth_response(user)


@router.get("/me", response_model=UserResponse)
def read_current_user(user: User = Depends(require("account"))) -> User:
    return user


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def forgot_password(
    payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """Start a password reset.

    Always returns the same 202 response. Telling the caller whether the
    address has an account would turn this endpoint into a way to harvest
    registered email addresses.
    """
    keys = limit_keys(request, str(payload.email).lower())
    refuse_if_limited(forgot_password_limiter, keys)
    for key in keys:
        forgot_password_limiter.record(key)
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
