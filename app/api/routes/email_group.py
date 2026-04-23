import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import EmailGroup

router = APIRouter(tags=["email-group"])
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailGroupCreateRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or not EMAIL_PATTERN.match(normalized):
            raise ValueError("Invalid email format.")
        return normalized


class EmailGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    created_at: datetime


@router.get("/email-group", response_model=list[EmailGroupResponse])
def list_email_group(db: Session = Depends(get_db)) -> list[EmailGroup]:
    return db.query(EmailGroup).order_by(EmailGroup.created_at.asc()).all()


@router.post("/email-group", response_model=EmailGroupResponse, status_code=status.HTTP_201_CREATED)
def add_email_group(payload: EmailGroupCreateRequest, db: Session = Depends(get_db)) -> EmailGroup:
    exists = db.query(EmailGroup).filter(EmailGroup.email == payload.email).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists.")

    row = EmailGroup(email=payload.email)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists.") from exc
    db.refresh(row)
    return row


@router.delete("/email-group/{email_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_email_group(email_id: str, db: Session = Depends(get_db)) -> None:
    row = db.query(EmailGroup).filter(EmailGroup.id == email_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found.")
    db.delete(row)
    db.commit()
