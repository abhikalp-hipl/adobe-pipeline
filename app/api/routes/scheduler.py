from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.db.database import SessionLocal
from app.db.models import NotificationSettings
from app.services.scheduler import Scheduler

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


class SchedulerStatusResponse(BaseModel):
    interval: int
    status: str
    provider: str
    automation_enabled: bool


class SchedulerIntervalUpdateRequest(BaseModel):
    interval: int = Field(ge=60)


class RunNowResponse(BaseModel):
    detail: str


def _get_scheduler(request: Request) -> Scheduler:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler is not initialized.",
        )
    return scheduler


@router.get("", response_model=SchedulerStatusResponse)
def get_scheduler_status(request: Request) -> SchedulerStatusResponse:
    scheduler = _get_scheduler(request=request)
    return SchedulerStatusResponse(
        interval=scheduler.interval,
        status=scheduler.status(),
        provider=scheduler.storage_provider,
        automation_enabled=scheduler.automation_enabled,
    )


@router.post("/interval", response_model=SchedulerStatusResponse)
def update_scheduler_interval(
    payload: SchedulerIntervalUpdateRequest,
    request: Request,
) -> SchedulerStatusResponse:
    scheduler = _get_scheduler(request=request)
    if not scheduler.automation_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scheduler interval updates are disabled for OneDrive delegated mode.",
        )
    scheduler.update_interval(new_interval=payload.interval)
    _persist_scheduler_interval(new_interval=payload.interval)
    return SchedulerStatusResponse(
        interval=scheduler.interval,
        status=scheduler.status(),
        provider=scheduler.storage_provider,
        automation_enabled=scheduler.automation_enabled,
    )


@router.post("/run-now", response_model=RunNowResponse)
def run_scheduler_now(request: Request) -> RunNowResponse:
    scheduler = _get_scheduler(request=request)
    scheduler.run_once()
    return RunNowResponse(detail="Processing started")


def _persist_scheduler_interval(new_interval: int) -> None:
    db = SessionLocal()
    try:
        settings_row = db.query(NotificationSettings).order_by(NotificationSettings.created_at.asc()).first()
        if not settings_row:
            settings_row = NotificationSettings(
                eod_time="18:00",
                enabled=False,
                scheduler_interval_seconds=new_interval,
            )
        else:
            settings_row.scheduler_interval_seconds = new_interval
        db.add(settings_row)
        db.commit()
    finally:
        db.close()
