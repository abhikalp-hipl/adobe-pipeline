import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.auth.microsoft_auth import MicrosoftAuthError, MicrosoftAuthService
from app.services.storage.onedrive import (
    INTAKE_FOLDER,
    PROCESSED_FOLDER,
    OUTPUT_SUCCESS_FOLDER,
    OUTPUT_FAILURE_FOLDER,
    OneDriveClient,
    OneDriveError,
    OneDriveNotFoundError,
)

router = APIRouter(tags=["files"])
logger = logging.getLogger(__name__)

FOLDER_MAP = {
    "intake": INTAKE_FOLDER,
    "processed": PROCESSED_FOLDER,
    "output/success": OUTPUT_SUCCESS_FOLDER,
    "output/failure": OUTPUT_FAILURE_FOLDER,
}


def _resolve_folder(folder: str) -> str:
    resolved = FOLDER_MAP.get(folder.lower())
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid folder. Use one of: intake, processed, output/success, output/failure.",
        )
    return resolved


@router.get("/files")
def list_files(folder: str = Query(...), db: Session = Depends(get_db)) -> list[dict]:
    folder_path = _resolve_folder(folder)
    logger.info("Files API listing OneDrive folder: folder=%s mapped_path=%s", folder, folder_path)
    auth_service = MicrosoftAuthService()
    onedrive_client = OneDriveClient()
    try:
        access_token = auth_service.get_valid_access_token(db=db)
        files = onedrive_client.list_files(access_token=access_token, folder_path=folder_path)
    except MicrosoftAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except OneDriveNotFoundError:
        return []
    except OneDriveError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    files_sorted = sorted(files, key=lambda item: item.get("last_modified", ""), reverse=True)
    response_payload = [
        {
            "id": item["id"],
            "name": item["name"],
            "type": "file",
            "mime_type": item.get("mime_type", "application/octet-stream"),
            "last_modified": item.get("last_modified", ""),
            "size_bytes": int(item.get("size_bytes") or 0),
        }
        for item in files_sorted
    ]
    logger.info("Files API response count: folder=%s count=%d", folder, len(response_payload))
    return response_payload


@router.get("/file-content")
def get_file_content(file_id: str = Query(..., alias="id"), db: Session = Depends(get_db)):
    auth_service = MicrosoftAuthService()
    onedrive_client = OneDriveClient()
    try:
        access_token = auth_service.get_valid_access_token(db=db)
        metadata = onedrive_client.get_item_metadata(access_token=access_token, file_id=file_id)
        mime_type = metadata.get("file", {}).get("mimeType", "application/octet-stream")
        filename = metadata.get("name", "download")
        content_response = onedrive_client.get_file_content(access_token=access_token, file_id=file_id)
    except MicrosoftAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except OneDriveNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OneDriveError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if filename.lower().endswith(".json") or mime_type == "application/json":
        try:
            return JSONResponse(content=json.loads(content_response.content.decode("utf-8")))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Invalid JSON file: {exc}") from exc

    headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    return StreamingResponse(content_response.iter_content(chunk_size=1024 * 1024), media_type=mime_type, headers=headers)


@router.get("/file-preview-pdf")
def get_file_preview_pdf(file_id: str = Query(..., alias="id"), db: Session = Depends(get_db)):
    auth_service = MicrosoftAuthService()
    onedrive_client = OneDriveClient()
    try:
        access_token = auth_service.get_valid_access_token(db=db)
        metadata = onedrive_client.get_item_metadata(access_token=access_token, file_id=file_id)
        filename = metadata.get("name", "document")
        mime_type = metadata.get("file", {}).get("mimeType", "application/octet-stream")
        lower_name = filename.lower()
        is_doc_file = lower_name.endswith(".docx") or lower_name.endswith(".doc") or mime_type in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        }
        if not is_doc_file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Preview PDF conversion supports DOC and DOCX only.",
            )
        pdf_response = onedrive_client.get_file_content_as_pdf(access_token=access_token, file_id=file_id)
    except MicrosoftAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except OneDriveNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OneDriveError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    preview_name = f"{filename.rsplit('.', 1)[0]}.preview.pdf" if "." in filename else "document.preview.pdf"
    return StreamingResponse(
        pdf_response.iter_content(chunk_size=1024 * 1024),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{preview_name}"'},
    )
