from collections.abc import Generator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.evaluation import CATALOG_CODE_PREFIX


def reject_reserved_code(code: str, current: str | None = None) -> None:
    """Refuse a catalogue code, unless the record already has it."""
    if code.upper().startswith(CATALOG_CODE_PREFIX) and code != current:
        raise HTTPException(
            status_code=422, detail=f"Codes starting {CATALOG_CODE_PREFIX} are reserved."
        )


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
