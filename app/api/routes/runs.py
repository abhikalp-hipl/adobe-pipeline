import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import PipelineRun, PipelineRunFile, PipelineRunStatus
from app.services.auth.microsoft_auth import MicrosoftAuthError, MicrosoftAuthService
from app.services.storage.onedrive import OUTPUT_SUCCESS_FOLDER, OneDriveClient, OneDriveError, OneDriveNotFoundError

router = APIRouter(tags=["runs"])


class PipelineRunListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    start_time: datetime
    duration: str
    total_files: int
    success_count: int
    failure_count: int
    status: PipelineRunStatus


class PipelineRunFileItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    status: PipelineRunStatus
    error: str
    outputs: dict[str, str | None]
    accessibility: dict[str, int]
    created_at: datetime


class PipelineRunDetailsResponse(BaseModel):
    run_id: str
    start_time: datetime
    duration: str
    total_files: int
    success_count: int
    failure_count: int
    status: PipelineRunStatus
    files: list[PipelineRunFileItem]


@router.get("/runs", response_model=list[PipelineRunListItem])
async def list_runs(db: AsyncSession = Depends(get_db)) -> list[PipelineRun]:
    return (await db.execute(select(PipelineRun).order_by(PipelineRun.start_time.desc()))).scalars().all()


@router.get("/runs/{run_id}/files", response_model=list[PipelineRunFileItem])
async def list_run_files(run_id: str, db: AsyncSession = Depends(get_db)) -> list[PipelineRunFile]:
    run = (await db.execute(select(PipelineRun).where(PipelineRun.run_id == run_id))).scalars().first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    rows = (
        await db.execute(select(PipelineRunFile).where(PipelineRunFile.run_id == run.id).order_by(PipelineRunFile.created_at.asc()))
    ).scalars().all()
    output_lookup, _grouped_outputs = await _build_output_catalog(db=db)
    response: list[PipelineRunFileItem] = []
    for row in rows:
        response.append(await _to_run_file_item(row, output_lookup=output_lookup))
    return response


@router.get("/runs/{run_id}", response_model=PipelineRunDetailsResponse)
async def get_run_details(run_id: str, db: AsyncSession = Depends(get_db)) -> PipelineRunDetailsResponse:
    run = (await db.execute(select(PipelineRun).where(PipelineRun.run_id == run_id))).scalars().first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    rows = (
        await db.execute(select(PipelineRunFile).where(PipelineRunFile.run_id == run.id).order_by(PipelineRunFile.created_at.asc()))
    ).scalars().all()
    output_lookup, _grouped_outputs = await _build_output_catalog(db=db)
    files: list[PipelineRunFileItem] = []
    for row in rows:
        files.append(await _to_run_file_item(row, output_lookup=output_lookup))
    return PipelineRunDetailsResponse(
        run_id=run.run_id,
        start_time=run.start_time,
        duration=run.duration,
        total_files=run.total_files,
        success_count=run.success_count,
        failure_count=run.failure_count,
        status=run.status,
        files=files,
    )


async def _to_run_file_item(
    row: PipelineRunFile,
    output_lookup: dict[str, str],
) -> PipelineRunFileItem:
    persisted_stem = (getattr(row, "output_stem", None) or "").strip()
    stem = persisted_stem or _derive_output_stem(row.file_name)
    pdf_id = _resolve_output_id(
        output_lookup,
        stem=stem,
        candidates=[f"{stem}_tagged_pdf.pdf", f"{stem}_tagged.pdf", f"{stem}.tagged.pdf"],
    )
    json_id = _resolve_output_id(
        output_lookup,
        stem=stem,
        candidates=[f"{stem}_accessibility_report.json", f"{stem}_report.json", f"{stem}.accessibility-report.json"],
    )
    xlsx_id = _resolve_output_id(
        output_lookup,
        stem=stem,
        candidates=[f"{stem}_tagged_report.xlsx", f"{stem}_report.xlsx", f"{stem}.autotag-report.xlsx"],
    )
    is_failed = row.status == PipelineRunStatus.FAILED
    if is_failed:
        pdf_id = ""
        json_id = ""
        xlsx_id = ""
    outputs = {
        "pdf_url": f"/file-content?id={pdf_id}" if pdf_id else None,
        "json_url": f"/file-content?id={json_id}" if json_id else None,
        "xlsx_url": f"/file-content?id={xlsx_id}" if xlsx_id else None,
    }
    stored_accessibility = {
        "passed": int(getattr(row, "accessibility_passed", 0) or 0),
        "failed": int(getattr(row, "accessibility_failed", 0) or 0),
        "manual": int(getattr(row, "accessibility_manual", 0) or 0),
    }
    has_non_zero_stored_values = any(value > 0 for value in stored_accessibility.values())
    if is_failed or not json_id or has_non_zero_stored_values:
        accessibility = stored_accessibility
    else:
        # Backward compatibility for older rows created before accessibility counters were persisted.
        accessibility = await _read_accessibility_counts(json_file_id=json_id)
    return PipelineRunFileItem(
        name=row.file_name,
        status=row.status,
        error=row.error_message,
        outputs=outputs,
        accessibility=accessibility,
        created_at=row.created_at,
    )


def _derive_output_stem(file_name: str) -> str:
    lower = (file_name or "").lower()
    if lower.endswith(".docx"):
        return file_name[:-5]
    if lower.endswith(".xlsx") or lower.endswith(".json"):
        return file_name.rsplit(".", 1)[0]
    if lower.endswith(".pdf") or lower.endswith(".doc"):
        return file_name.rsplit(".", 1)[0]
    return file_name


async def _build_output_catalog(db: AsyncSession) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    auth_service = MicrosoftAuthService()
    onedrive_client = OneDriveClient()
    try:
        access_token = await auth_service.get_valid_access_token(db=db)
        files = await onedrive_client.list_files(access_token=access_token, folder_path=OUTPUT_SUCCESS_FOLDER)
        lookup = {item.get("name", ""): item.get("id", "") for item in files if item.get("name") and item.get("id")}
        grouped: dict[str, dict[str, str]] = {}
        for item in files:
            name = str(item.get("name") or "")
            file_id = str(item.get("id") or "")
            if not name or not file_id:
                continue
            if name.endswith("_tagged_pdf.pdf"):
                key = name[: -len("_tagged_pdf.pdf")]
                grouped.setdefault(key, {})["pdf"] = file_id
            elif name.endswith("_tagged.pdf"):
                key = name[: -len("_tagged.pdf")]
                grouped.setdefault(key, {})["pdf"] = file_id
            elif name.endswith("_accessibility_report.json"):
                key = name[: -len("_accessibility_report.json")]
                grouped.setdefault(key, {})["json"] = file_id
            elif name.endswith("_report.json"):
                key = name[: -len("_report.json")]
                grouped.setdefault(key, {})["json"] = file_id
            elif name.endswith("_tagged_report.xlsx"):
                key = name[: -len("_tagged_report.xlsx")]
                grouped.setdefault(key, {})["xlsx"] = file_id
            elif name.endswith("_report.xlsx"):
                key = name[: -len("_report.xlsx")]
                grouped.setdefault(key, {})["xlsx"] = file_id
            elif name.endswith(".autotag-report.xlsx"):
                key = name[: -len(".autotag-report.xlsx")]
                grouped.setdefault(key, {})["xlsx"] = file_id
        grouped = {k: v for k, v in grouped.items() if v.get("pdf") or v.get("json") or v.get("xlsx")}
        return lookup, grouped
    except (MicrosoftAuthError, OneDriveError, OneDriveNotFoundError):
        return {}, {}


def _resolve_output_id(output_lookup: dict[str, str], stem: str, candidates: list[str]) -> str:
    for name in candidates:
        file_id = output_lookup.get(name, "")
        if file_id:
            return file_id
    # Intentionally no substring fuzzy match: short stems (and substrings like "report")
    # incorrectly resolve to the first OneDrive output and duplicate accessibility counts.
    return ""


async def _read_accessibility_counts(json_file_id: str) -> dict[str, int]:
    if not json_file_id:
        return {"passed": 0, "failed": 0, "manual": 0}
    async for db in get_db():
        try:
            auth_service = MicrosoftAuthService()
            onedrive_client = OneDriveClient()
            access_token = await auth_service.get_valid_access_token(db=db)
            content = await onedrive_client.get_file_content(access_token=access_token, file_id=json_file_id)
            payload = json.loads(content.decode("utf-8"))
            summary = payload.get("Summary") if isinstance(payload, dict) else {}
            return {
                "passed": int((summary or {}).get("Passed", 0)) + int((summary or {}).get("Passed manually", 0)),
                "failed": int((summary or {}).get("Failed", 0)) + int((summary or {}).get("Failed manually", 0)),
                "manual": int((summary or {}).get("Needs manual check", 0)),
            }
        except Exception:
            return {"passed": 0, "failed": 0, "manual": 0}
    return {"passed": 0, "failed": 0, "manual": 0}
