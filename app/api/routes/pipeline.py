from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Document, DocumentStatus
from app.services.scheduler import Scheduler

router = APIRouter(tags=["pipeline"])
ACTIVE_WINDOW_SECONDS = 120


class PipelineStatusResponse(BaseModel):
    is_running: bool
    current_step: str | None = None
    current_file: str | None = None
    progress: int = 0
    error: str | None = None
    failed_step: str | None = None


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


@router.post("/run-now", response_model=RunNowResponse)
def run_now(request: Request) -> RunNowResponse:
    scheduler = _get_scheduler(request=request)
    scheduler.run_once()
    return RunNowResponse(detail="Processing started")


@router.get("/pipeline/status", response_model=PipelineStatusResponse)
def get_pipeline_status(request: Request, db: Session = Depends(get_db)) -> PipelineStatusResponse:
    progress_map: dict[DocumentStatus, int] = {
        DocumentStatus.UPLOADED: 10,
        DocumentStatus.PROCESSING: 30,
        DocumentStatus.TAGGED: 60,
        DocumentStatus.CHECKED: 80,
        DocumentStatus.COMPLETED: 100,
        DocumentStatus.FAILED: 100,
    }
    running_statuses = (
        DocumentStatus.UPLOADED,
        DocumentStatus.PROCESSING,
        DocumentStatus.TAGGED,
        DocumentStatus.CHECKED,
    )

    current: Document | None = (
        db.query(Document)
        .filter(Document.status.in_(running_statuses))
        .order_by(Document.updated_at.desc())
        .first()
    )
    if current is None:
        scheduler = getattr(request.app.state, "scheduler", None)
        failure = getattr(scheduler, "last_failure", None) if scheduler else None
        if (
            failure
            and failure.get("at")
            and failure["at"] > datetime.now(UTC) - timedelta(seconds=ACTIVE_WINDOW_SECONDS)
        ):
            return PipelineStatusResponse(
                is_running=False,
                current_step="FAILED",
                current_file=failure.get("current_file"),
                progress=int(failure.get("progress") or 0),
                error=failure.get("error"),
                failed_step=failure.get("failed_step"),
            )
        # Surface a recent completion so the UI can toast success.
        completed: Document | None = (
            db.query(Document)
            .filter(Document.status == DocumentStatus.COMPLETED)
            .order_by(Document.updated_at.desc())
            .first()
        )
        if completed is not None:
            completed_updated = completed.updated_at
            if completed_updated.tzinfo is None:
                completed_updated = completed_updated.replace(tzinfo=UTC)
            if completed_updated > datetime.now(UTC) - timedelta(seconds=ACTIVE_WINDOW_SECONDS):
                return PipelineStatusResponse(
                    is_running=False,
                    current_step="COMPLETED",
                    current_file=completed.filename,
                    progress=100,
                )
        return PipelineStatusResponse(is_running=False, current_step=None, current_file=None, progress=0)

    # Treat stale intermediate states as idle to avoid false "running" UI.
    updated_at = current.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    if updated_at < datetime.now(UTC) - timedelta(seconds=ACTIVE_WINDOW_SECONDS):
        return PipelineStatusResponse(is_running=False, current_step=None, current_file=None, progress=0)

    return PipelineStatusResponse(
        is_running=True,
        current_step=current.status.value,
        current_file=current.filename,
        progress=progress_map.get(current.status, 0),
    )

