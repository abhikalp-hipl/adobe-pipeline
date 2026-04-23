import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

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
def list_runs(db: Session = Depends(get_db)) -> list[PipelineRun]:
    return db.query(PipelineRun).order_by(PipelineRun.start_time.desc()).all()


@router.get("/runs/{run_id}/files", response_model=list[PipelineRunFileItem])
def list_run_files(run_id: str, db: Session = Depends(get_db)) -> list[PipelineRunFile]:
    run = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    rows = db.query(PipelineRunFile).filter(PipelineRunFile.run_id == run.id).order_by(PipelineRunFile.created_at.asc()).all()
    output_lookup, grouped_outputs = _build_output_catalog(db=db)
    fallback_groups = list(grouped_outputs.values())
    response: list[PipelineRunFileItem] = []
    for idx, row in enumerate(rows):
        fallback = fallback_groups[idx] if idx < len(fallback_groups) else None
        response.append(_to_run_file_item(row, output_lookup=output_lookup, fallback_bundle=fallback))
    return response


@router.get("/runs/{run_id}", response_model=PipelineRunDetailsResponse)
def get_run_details(run_id: str, db: Session = Depends(get_db)) -> PipelineRunDetailsResponse:
    run = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    rows = db.query(PipelineRunFile).filter(PipelineRunFile.run_id == run.id).order_by(PipelineRunFile.created_at.asc()).all()
    output_lookup, grouped_outputs = _build_output_catalog(db=db)
    fallback_groups = list(grouped_outputs.values())
    files: list[PipelineRunFileItem] = []
    for idx, row in enumerate(rows):
        fallback = fallback_groups[idx] if idx < len(fallback_groups) else None
        files.append(_to_run_file_item(row, output_lookup=output_lookup, fallback_bundle=fallback))
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


def _to_run_file_item(
    row: PipelineRunFile,
    output_lookup: dict[str, str],
    fallback_bundle: dict[str, str] | None = None,
) -> PipelineRunFileItem:
    stem = _derive_output_stem(row.file_name)
    pdf_id = _resolve_output_id(
        output_lookup,
        stem=stem,
        candidates=[f"{stem}_tagged_pdf.pdf", f"{stem}_tagged.pdf", f"{stem}.tagged.pdf"],
        ext=".pdf",
    )
    json_id = _resolve_output_id(
        output_lookup,
        stem=stem,
        candidates=[f"{stem}_accessibility_report.json", f"{stem}_report.json", f"{stem}.accessibility-report.json"],
        ext=".json",
    )
    xlsx_id = _resolve_output_id(
        output_lookup,
        stem=stem,
        candidates=[f"{stem}_tagged_report.xlsx", f"{stem}_report.xlsx", f"{stem}.autotag-report.xlsx"],
        ext=".xlsx",
    )
    is_failed = row.status == PipelineRunStatus.FAILED
    if is_failed:
        pdf_id = ""
        json_id = ""
        xlsx_id = ""
    elif fallback_bundle:
        pdf_id = pdf_id or fallback_bundle.get("pdf", "")
        json_id = json_id or fallback_bundle.get("json", "")
        xlsx_id = xlsx_id or fallback_bundle.get("xlsx", "")
    outputs = {
        "pdf_url": f"/file-content?id={pdf_id}" if pdf_id else None,
        "json_url": f"/file-content?id={json_id}" if json_id else None,
        "xlsx_url": f"/file-content?id={xlsx_id}" if xlsx_id else None,
    }
    accessibility = {"passed": 0, "failed": 0, "manual": 0} if is_failed else _read_accessibility_counts(json_file_id=json_id)
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


def _build_output_catalog(db: Session) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    auth_service = MicrosoftAuthService()
    onedrive_client = OneDriveClient()
    try:
        access_token = auth_service.get_valid_access_token(db=db)
        files = onedrive_client.list_files(access_token=access_token, folder_path=OUTPUT_SUCCESS_FOLDER)
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


def _resolve_output_id(output_lookup: dict[str, str], stem: str, candidates: list[str], ext: str) -> str:
    for name in candidates:
        file_id = output_lookup.get(name, "")
        if file_id:
            return file_id

    # Fallback: tolerant matching for naming variants in output/success.
    normalized_stem = stem.lower().replace(" ", "").replace("_", "").replace("-", "")
    for name, file_id in output_lookup.items():
        lower_name = name.lower()
        if not lower_name.endswith(ext):
            continue
        normalized_name = lower_name.replace(" ", "").replace("_", "").replace("-", "")
        if normalized_stem and normalized_stem in normalized_name:
            return file_id
    return ""


def _read_accessibility_counts(json_file_id: str) -> dict[str, int]:
    if not json_file_id:
        return {"passed": 0, "failed": 0, "manual": 0}
    db = next(get_db())
    try:
        auth_service = MicrosoftAuthService()
        onedrive_client = OneDriveClient()
        access_token = auth_service.get_valid_access_token(db=db)
        response = onedrive_client.get_file_content(access_token=access_token, file_id=json_file_id)
        payload = json.loads(response.content.decode("utf-8"))
        summary = payload.get("Summary") if isinstance(payload, dict) else {}
        return {
            "passed": int((summary or {}).get("Passed", 0)) + int((summary or {}).get("Passed manually", 0)),
            "failed": int((summary or {}).get("Failed", 0)) + int((summary or {}).get("Failed manually", 0)),
            "manual": int((summary or {}).get("Needs manual check", 0)),
        }
    except Exception:
        return {"passed": 0, "failed": 0, "manual": 0}
    finally:
        db.close()
