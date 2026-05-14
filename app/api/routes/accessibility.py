import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.auth.microsoft_auth import MicrosoftAuthError, MicrosoftAuthService
from app.services.pdf.locator import enrich_report
from app.services.storage.onedrive import OneDriveClient, OneDriveError, OneDriveNotFoundError

router = APIRouter(tags=["accessibility"])
logger = logging.getLogger(__name__)


class FailureLocation(BaseModel):
    model_config = ConfigDict(extra="allow")

    category: str = ""
    rule: str = ""
    status: str = ""
    description: str = ""
    scope: str | None = None
    review_hint: str | None = None


class EnrichedReportResponse(BaseModel):
    summary: dict[str, object] = Field(default_factory=dict)
    failures_by_page: dict[str, list[FailureLocation]] = Field(default_factory=dict)
    unlocatable_failures: list[FailureLocation] = Field(default_factory=list)
    manual_check_required: list[FailureLocation] = Field(default_factory=list)


def _failure_locations_from_dicts(items: object) -> list[FailureLocation]:
    if not isinstance(items, list):
        return []
    return [FailureLocation.model_validate(x) for x in items if isinstance(x, dict)]


def _failures_by_page_from_raw(raw: object) -> dict[str, list[FailureLocation]]:
    if not isinstance(raw, dict):
        return {}
    return {
        str(k): _failure_locations_from_dicts(v)
        for k, v in raw.items()
        if isinstance(v, list)
    }


@router.get("/accessibility-detail", response_model=EnrichedReportResponse)
async def accessibility_detail(
    pdf_id: str = Query(..., min_length=1, description="OneDrive file id for tagged PDF"),
    json_id: str = Query(..., min_length=1, description="OneDrive file id for accessibility report JSON"),
    db: AsyncSession = Depends(get_db),
) -> EnrichedReportResponse:
    """
    Download tagged PDF + Adobe accessibility JSON from OneDrive, then attach per-page
    localization (where struct-tree rules allow it).
    """
    auth_service = MicrosoftAuthService()
    onedrive_client = OneDriveClient()
    tmp_path: Path | None = None
    try:
        access_token = await auth_service.get_valid_access_token(db=db)
    except MicrosoftAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        pdf_bytes = await onedrive_client.get_file_content(access_token=access_token, file_id=pdf_id)
        json_bytes = await onedrive_client.get_file_content(access_token=access_token, file_id=json_id)
    except OneDriveNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OneDrive file not found.") from exc
    except OneDriveError as exc:
        logger.exception("accessibility_detail OneDrive download failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    try:
        payload = json.loads(json_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Accessibility report is not valid JSON.",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Accessibility report must be a JSON object.",
        )

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = Path(tmp.name)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not stage PDF for analysis.",
        ) from exc

    try:
        raw = enrich_report(payload, tmp_path)
        return EnrichedReportResponse(
            summary=dict(raw.get("summary") or {}),
            failures_by_page=_failures_by_page_from_raw(raw.get("failures_by_page")),
            unlocatable_failures=_failure_locations_from_dicts(raw.get("unlocatable_failures")),
            manual_check_required=_failure_locations_from_dicts(raw.get("manual_check_required")),
        )
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to delete temp PDF: path=%s", tmp_path)
