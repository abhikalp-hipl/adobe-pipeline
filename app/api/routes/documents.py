import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.schemas.document import DocumentResponse
from app.services.adobe.client import AdobeAPIError
from app.services.auth.microsoft_auth import MicrosoftAuthError
from app.services.document_service import (
    DocumentServiceError,
    get_document_by_id,
    list_documents,
    upload_document,
)
from app.services.orchestrator import DocumentNotFoundError, Orchestrator, OrchestratorError
from app.services.scheduler import Scheduler
from app.services.storage.onedrive import OneDriveAuthError, OneDriveError

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document_endpoint(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    if settings.STORAGE_PROVIDER == "onedrive":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Local upload is disabled in OneDrive-only mode. Use OneDrive intake processing.",
        )
    logger.info("Upload request received: filename=%s", file.filename)
    try:
        document = await upload_document(file=file, db=db)
        logger.info("Upload completed: document_id=%s status=%s", document.id, document.status.value)
        return DocumentResponse.model_validate(document)
    except HTTPException:
        raise
    except DocumentServiceError as exc:
        logger.exception("Upload failed: filename=%s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[DocumentResponse])
async def list_documents_endpoint(db: AsyncSession = Depends(get_db)) -> list[DocumentResponse]:
    documents = await list_documents(db=db)
    logger.info("List documents request completed: count=%d", len(documents))
    return [DocumentResponse.model_validate(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_endpoint(
    document_id: str,
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    document = await get_document_by_id(document_id=document_id, db=db)
    logger.info("Get document request completed: document_id=%s status=%s", document.id, document.status.value)
    return DocumentResponse.model_validate(document)


@router.post("/{document_id}/process")
async def process_document_endpoint(
    document_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    if settings.STORAGE_PROVIDER == "onedrive":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manual local processing is disabled in OneDrive-only mode. Use /documents/onedrive/process-intake.",
        )
    logger.info("Process request received: document_id=%s", document_id)
    orchestrator = Orchestrator(db=db)
    try:
        result = await orchestrator.process_document(document_id=document_id)
        logger.info("Process request completed: document_id=%s status=%s", document_id, result["status"])
        return result
    except DocumentNotFoundError as exc:
        logger.warning("Process request failed (not found): document_id=%s", document_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AdobeAPIError as exc:
        logger.exception("Process request failed (Adobe API): document_id=%s", document_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Adobe API error: {exc}",
        ) from exc
    except OrchestratorError as exc:
        logger.exception("Process request failed (orchestrator): document_id=%s", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post("/onedrive/process-intake")
async def process_onedrive_intake_endpoint(
) -> dict[str, int]:
    if settings.STORAGE_PROVIDER != "onedrive":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OneDrive intake processing is only available when STORAGE_PROVIDER=onedrive.",
        )

    scheduler = Scheduler()
    try:
        return await scheduler.process_onedrive_intake()
    except OneDriveAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except MicrosoftAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except OneDriveError as exc:
        logger.exception("OneDrive intake processing failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
