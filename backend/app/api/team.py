from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require
from app.core.security import hash_password
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.schemas.team import TeamMember, TeamMemberCreate, TeamMemberRole

router = APIRouter(prefix="/team", tags=["team"])
EMAIL_TAKEN = "An account with this email already exists."


def _get_member(db: Session, member_id: int, planner: User) -> User:
    # A planner's own account is not a member, so this also stops them
    # changing their own role.
    member = db.scalar(select(User).where(User.id == member_id, User.planner_id == planner.id))
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    return member


@router.get("", response_model=list[TeamMember])
def list_team(
    db: Session = Depends(get_db), planner: User = Depends(require("team.manage"))
) -> list[User]:
    return list(db.scalars(select(User).where(User.planner_id == planner.id).order_by(User.name)))


@router.post("", response_model=TeamMember, status_code=status.HTTP_201_CREATED)
def create_team_member(
    payload: TeamMemberCreate,
    db: Session = Depends(get_db),
    planner: User = Depends(require("team.manage")),
) -> User:
    email = str(payload.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EMAIL_TAKEN)
    member = User(
        name=payload.name, email=email, hashed_password=hash_password(payload.password),
        role=payload.role, planner_id=planner.id,
    )
    db.add(member)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EMAIL_TAKEN) from None
    db.refresh(member)
    return member


@router.put("/{member_id}", response_model=TeamMember)
def change_team_member_role(
    member_id: int,
    payload: TeamMemberRole,
    db: Session = Depends(get_db),
    planner: User = Depends(require("team.manage")),
) -> User:
    member = _get_member(db, member_id, planner)
    member.role = payload.role
    db.commit()
    return member


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_team_member(
    member_id: int,
    db: Session = Depends(get_db),
    planner: User = Depends(require("team.manage")),
) -> Response:
    member = _get_member(db, member_id, planner)
    # SQLite does not enforce the foreign key cascade.
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == member.id))
    db.delete(member)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
