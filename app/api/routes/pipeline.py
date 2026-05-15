from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.services.auth.app_auth import CurrentUser, require_dept_user
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
async def run_now(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_dept_user)],
) -> RunNowResponse:
    scheduler = _get_scheduler(request=request)
    await scheduler.run_once(department_id=user.department_id)
    return RunNowResponse(detail="Processing completed")
