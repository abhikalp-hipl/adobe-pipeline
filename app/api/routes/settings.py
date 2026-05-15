import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import NotificationSettings
from app.services.auth.app_auth import CurrentUser, require_dept_user

router = APIRouter(tags=["settings"])
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class NotificationSettingsPayload(BaseModel):
    eod_time: str
    enabled: bool

    @field_validator("eod_time")
    @classmethod
    def validate_eod_time(cls, value: str) -> str:
        normalized = value.strip()
        if not TIME_PATTERN.match(normalized):
            raise ValueError("Invalid time format. Use HH:mm.")
        return normalized


class NotificationSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    eod_time: str
    enabled: bool
    scheduler_interval_seconds: int


async def _get_or_create_settings(db: AsyncSession, department_id: str) -> NotificationSettings:
    settings_row = (
        await db.execute(select(NotificationSettings).where(NotificationSettings.department_id == department_id))
    ).scalars().first()
    if settings_row:
        return settings_row
    settings_row = NotificationSettings(
        eod_time="18:00",
        enabled=False,
        scheduler_interval_seconds=300,
        department_id=department_id,
    )
    db.add(settings_row)
    await db.commit()
    await db.refresh(settings_row)
    return settings_row


@router.get("/settings", response_model=NotificationSettingsResponse)
async def get_settings(
    user: Annotated[CurrentUser, Depends(require_dept_user)],
    db: AsyncSession = Depends(get_db),
) -> NotificationSettings:
    return await _get_or_create_settings(db=db, department_id=user.department_id)


@router.post("/settings", response_model=NotificationSettingsResponse)
async def update_settings(
    payload: NotificationSettingsPayload,
    user: Annotated[CurrentUser, Depends(require_dept_user)],
    db: AsyncSession = Depends(get_db),
) -> NotificationSettings:
    settings_row = await _get_or_create_settings(db=db, department_id=user.department_id)
    settings_row.eod_time = payload.eod_time
    settings_row.enabled = payload.enabled
    db.add(settings_row)
    await db.commit()
    await db.refresh(settings_row)
    return settings_row
