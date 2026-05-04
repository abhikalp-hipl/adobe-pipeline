from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.services.scheduler import Scheduler

router = APIRouter(tags=["pipeline"])

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
async def run_now(request: Request) -> RunNowResponse:
    scheduler = _get_scheduler(request=request)
    await scheduler.run_once()
    return RunNowResponse(detail="Processing completed")

