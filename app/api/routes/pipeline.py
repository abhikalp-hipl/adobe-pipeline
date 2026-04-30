from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from app.services.scheduler import Scheduler

router = APIRouter(tags=["pipeline"])


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
async def run_now(request: Request) -> RunNowResponse:
    scheduler = _get_scheduler(request=request)
    await scheduler.run_once()
    return RunNowResponse(detail="Processing started")


@router.get("/pipeline/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(request: Request) -> PipelineStatusResponse:
    scheduler = _get_scheduler(request=request)
    status_payload = scheduler.get_pipeline_status()
    return PipelineStatusResponse(
        is_running=bool(status_payload.get("is_running", False)),
        current_step=status_payload.get("current_step"),
        current_file=status_payload.get("current_file"),
        progress=int(status_payload.get("progress") or 0),
        error=status_payload.get("error"),
        failed_step=status_payload.get("failed_step"),
    )


@router.websocket("/ws/pipeline")
async def pipeline_status_ws(websocket: WebSocket) -> None:
    ws_manager = getattr(websocket.app.state, "pipeline_ws_manager", None)
    scheduler = getattr(websocket.app.state, "scheduler", None)
    if ws_manager is None or scheduler is None:
        await websocket.close(code=1011)
        return

    await ws_manager.connect(websocket)
    await websocket.send_json(
        {
            "type": "status",
            **scheduler.get_pipeline_status(),
        }
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)

