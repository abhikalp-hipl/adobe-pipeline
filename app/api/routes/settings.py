import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import NotificationSettings

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


def _get_or_create_settings(db: Session) -> NotificationSettings:
    settings_row = db.query(NotificationSettings).order_by(NotificationSettings.created_at.asc()).first()
    if settings_row:
        return settings_row
    settings_row = NotificationSettings(eod_time="18:00", enabled=False, scheduler_interval_seconds=300)
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row


@router.get("/settings", response_model=NotificationSettingsResponse)
def get_settings(db: Session = Depends(get_db)) -> NotificationSettings:
    return _get_or_create_settings(db=db)


@router.post("/settings", response_model=NotificationSettingsResponse)
def update_settings(payload: NotificationSettingsPayload, db: Session = Depends(get_db)) -> NotificationSettings:
    settings_row = _get_or_create_settings(db=db)
    settings_row.eod_time = payload.eod_time
    settings_row.enabled = payload.enabled
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row
