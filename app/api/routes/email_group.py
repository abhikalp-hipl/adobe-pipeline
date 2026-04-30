import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
async def list_email_group(db: AsyncSession = Depends(get_db)) -> list[EmailGroup]:
    return (await db.execute(select(EmailGroup).order_by(EmailGroup.created_at.asc()))).scalars().all()


@router.post("/email-group", response_model=EmailGroupResponse, status_code=status.HTTP_201_CREATED)
async def add_email_group(payload: EmailGroupCreateRequest, db: AsyncSession = Depends(get_db)) -> EmailGroup:
    exists = (await db.execute(select(EmailGroup).where(EmailGroup.email == payload.email))).scalars().first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists.")

    row = EmailGroup(email=payload.email)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists.") from exc
    await db.refresh(row)
    return row


@router.delete("/email-group/{email_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email_group(email_id: str, db: AsyncSession = Depends(get_db)) -> None:
    row = (await db.execute(select(EmailGroup).where(EmailGroup.id == email_id))).scalars().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found.")
    await db.delete(row)
    await db.commit()
