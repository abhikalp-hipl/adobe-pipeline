from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentStatus

INTAKE_DIR = Path("storage/intake")


class DocumentServiceError(Exception):
    pass


def upload_document(file: UploadFile, db: Session) -> Document:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is missing in upload request.",
        )

    INTAKE_DIR.mkdir(parents=True, exist_ok=True)

    document_id = str(uuid4())
    safe_filename = Path(file.filename).name
    stored_filename = f"{document_id}_{safe_filename}"
    destination = INTAKE_DIR / stored_filename

    try:
        with destination.open("wb") as buffer:
            while chunk := file.file.read(1024 * 1024):
                buffer.write(chunk)
    except OSError as exc:
        raise DocumentServiceError("Failed to store uploaded file.") from exc
    finally:
        file.file.close()

    document = Document(
        id=document_id,
        filename=stored_filename,
        status=DocumentStatus.UPLOADED,
    )

    try:
        db.add(document)
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise DocumentServiceError("Failed to persist document metadata.") from exc

    return document


def list_documents(db: Session) -> list[Document]:
    return db.query(Document).order_by(Document.created_at.desc()).all()


def get_document_by_id(document_id: str, db: Session) -> Document:
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' was not found.",
        )
    return document
