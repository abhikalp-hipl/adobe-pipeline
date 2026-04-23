import json
import logging
import shutil
import tempfile
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentStatus
from app.services.adobe.client import AdobeClient
from app.services.precheck import validate_pdf

logger = logging.getLogger(__name__)

INTAKE_DIR = Path("storage/intake")
PROCESSED_DIR = Path("storage/processed")
OUTPUT_SUCCESS_DIR = Path("storage/output/success")
OUTPUT_FAILURE_DIR = Path("storage/output/failure")


class OrchestratorError(Exception):
    pass


class DocumentNotFoundError(OrchestratorError):
    pass


class Orchestrator:
    def __init__(self, db: Session, adobe_client: AdobeClient | None = None) -> None:
        self.db = db
        self.adobe_client = adobe_client or AdobeClient()
        self._ensure_directories()
        logger.info("Orchestrator initialized")

    def process_document(self, document_id: str, input_path: str | Path | None = None) -> dict[str, str]:
        logger.info("Pipeline start: document_id=%s", document_id)
        document = self._get_document(document_id)
        intake_path = Path(input_path) if input_path else INTAKE_DIR / document.filename
        logger.info("Step fetch document: document_id=%s status=%s file=%s", document.id, document.status.value, intake_path)

        if not intake_path.exists():
            self._set_status(document, DocumentStatus.FAILED)
            logger.error("Step file check failed: missing intake file for document_id=%s path=%s", document.id, intake_path)
            err = OrchestratorError(f"Input file not found in intake storage: {intake_path}")
            setattr(err, "failed_step", "fetch")
            raise err

        failed_step = "start"
        original_name = self._derive_original_name(document.filename, intake_path.name)
        base_name = Path(original_name).stem
        tagged_output_path = OUTPUT_SUCCESS_DIR / f"{base_name}_tagged_pdf.pdf"
        report_output_path = OUTPUT_SUCCESS_DIR / f"{base_name}_accessibility_report.json"
        xlsx_report_output_path = OUTPUT_SUCCESS_DIR / f"{base_name}_tagged_report.xlsx"
        try:
            self._set_status(document, DocumentStatus.PROCESSING)
            logger.info("Step status update: document_id=%s status=%s", document.id, DocumentStatus.PROCESSING.value)

            # Step 0: convert non-PDF to PDF.
            failed_step = "convert_to_pdf"
            pdf_path = intake_path
            if intake_path.suffix.lower() != ".pdf":
                logger.info("Step convert_to_pdf start: document_id=%s input=%s", document.id, intake_path)
                with tempfile.TemporaryDirectory(prefix="adobe-pipeline-") as temp_dir:
                    pdf_path = self.adobe_client.convert_to_pdf(
                        intake_path,
                        output_dir=Path(temp_dir),
                    )
                    failed_step = "precheck"
                    precheck = validate_pdf(pdf_path)
                    if not precheck.get("valid", False):
                        message = str(precheck.get("reason") or "PDF precheck failed.")
                        logger.warning(
                            "Step precheck failed: document_id=%s type=%s reason=%s",
                            document.id,
                            precheck.get("type", ""),
                            message,
                        )
                        raise OrchestratorError(message)
                    # Step 1: auto-tag.
                    failed_step = "auto_tag"
                    logger.info("Step auto_tag start: document_id=%s input=%s", document.id, pdf_path)
                    generated_tagged_path, autotag_report_path = self.adobe_client.auto_tag(
                        pdf_path,
                        output_dir=OUTPUT_SUCCESS_DIR,
                        report_dir=OUTPUT_SUCCESS_DIR,
                    )
                    logger.info("Step auto_tag done: document_id=%s tagged_output=%s", document.id, generated_tagged_path)
                    if generated_tagged_path != tagged_output_path:
                        tagged_output_path = generated_tagged_path.replace(tagged_output_path)
                    if autotag_report_path and autotag_report_path != xlsx_report_output_path:
                        xlsx_report_output_path.parent.mkdir(parents=True, exist_ok=True)
                        xlsx_report_output_path = autotag_report_path.replace(xlsx_report_output_path)
            else:
                logger.info("Step convert_to_pdf skipped: document_id=%s input already pdf", document.id)
                failed_step = "precheck"
                precheck = validate_pdf(pdf_path)
                if not precheck.get("valid", False):
                    message = str(precheck.get("reason") or "PDF precheck failed.")
                    logger.warning(
                        "Step precheck failed: document_id=%s type=%s reason=%s",
                        document.id,
                        precheck.get("type", ""),
                        message,
                    )
                    raise OrchestratorError(message)

                # Step 1: auto-tag.
                failed_step = "auto_tag"
                logger.info("Step auto_tag start: document_id=%s input=%s", document.id, pdf_path)
                generated_tagged_path, autotag_report_path = self.adobe_client.auto_tag(
                    pdf_path,
                    output_dir=OUTPUT_SUCCESS_DIR,
                    report_dir=OUTPUT_SUCCESS_DIR,
                )
                logger.info("Step auto_tag done: document_id=%s tagged_output=%s", document.id, generated_tagged_path)
                if generated_tagged_path != tagged_output_path:
                    tagged_output_path = generated_tagged_path.replace(tagged_output_path)
                if autotag_report_path and autotag_report_path != xlsx_report_output_path:
                    xlsx_report_output_path.parent.mkdir(parents=True, exist_ok=True)
                    xlsx_report_output_path = autotag_report_path.replace(xlsx_report_output_path)
                logger.info("Step convert_to_pdf done: document_id=%s output=%s", document.id, pdf_path)
            self._set_status(document, DocumentStatus.TAGGED)
            logger.info("Step status update: document_id=%s status=%s", document.id, DocumentStatus.TAGGED.value)

            # Step 2: accessibility check.
            failed_step = "check_accessibility"
            logger.info("Step accessibility_check start: document_id=%s input=%s", document.id, tagged_output_path)
            generated_report_path = self.adobe_client.check_accessibility(
                tagged_output_path,
                report_dir=OUTPUT_SUCCESS_DIR,
            )
            if generated_report_path != report_output_path:
                report_output_path = generated_report_path.replace(report_output_path)
            logger.info("Step accessibility_check done: document_id=%s report_output=%s", document.id, report_output_path)
            self._set_status(document, DocumentStatus.CHECKED)
            logger.info("Step status update: document_id=%s status=%s", document.id, DocumentStatus.CHECKED.value)

            processed_original_path = self._move_original_to_processed(intake_path, original_name)
            logger.info("File moved to processed: source=%s destination=%s", intake_path, processed_original_path)
            logger.info(
                "Pipeline output paths: tagged_pdf=%s report_json=%s report_xlsx=%s",
                tagged_output_path,
                report_output_path,
                xlsx_report_output_path,
            )

            # Step 3: completed.
            self._set_status(document, DocumentStatus.COMPLETED)
            logger.info("Step status update: document_id=%s status=%s", document.id, DocumentStatus.COMPLETED.value)
            logger.info("Pipeline completed: document_id=%s", document.id)
            return {
                "document_id": document.id,
                "status": DocumentStatus.COMPLETED.value,
                "tagged_pdf_path": str(tagged_output_path),
                "report_path": str(report_output_path),
                "autotag_report_path": str(xlsx_report_output_path) if xlsx_report_output_path.exists() else "",
                "processed_original_path": str(processed_original_path),
            }
        except Exception as exc:
            failed_destination = self._move_original_to_failure(intake_path, original_name)
            self._set_status(document, DocumentStatus.FAILED)
            logger.exception("Pipeline failed: document_id=%s failed_destination=%s", document.id, failed_destination)
            self._write_error_log(original_name=original_name, failed_step=failed_step, error=str(exc))
            err = OrchestratorError(str(exc) or "Document processing failed.")
            setattr(err, "failed_step", failed_step)
            setattr(err, "failed_destination", str(failed_destination))
            raise err from exc

    def _get_document(self, document_id: str) -> Document:
        document = self.db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning("Document lookup failed: document_id=%s", document_id)
            raise DocumentNotFoundError(f"Document '{document_id}' was not found.")
        return document

    def _set_status(self, document: Document, status: DocumentStatus) -> None:
        try:
            previous_status = document.status.value if document.status else "UNKNOWN"
            document.status = status
            self.db.add(document)
            self.db.commit()
            self.db.refresh(document)
            logger.info(
                "Status transition: document_id=%s from=%s to=%s",
                document.id,
                previous_status,
                status.value,
            )
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise OrchestratorError(
                f"Failed to update document status to '{status.value}'."
            ) from exc

    @staticmethod
    def _ensure_directories() -> None:
        INTAKE_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_SUCCESS_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_FAILURE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Storage directories ensured: intake=%s processed=%s output_success=%s output_failure=%s",
            INTAKE_DIR,
            PROCESSED_DIR,
            OUTPUT_SUCCESS_DIR,
            OUTPUT_FAILURE_DIR,
        )

    @staticmethod
    def _derive_original_name(stored_name: str, fallback_name: str) -> str:
        candidate = Path(stored_name).name or Path(fallback_name).name
        parts = candidate.split("_", 1)
        if len(parts) == 2 and len(parts[0]) >= 8:
            return parts[1]
        return candidate

    @staticmethod
    def _move_original_to_processed(intake_path: Path, original_name: str) -> Path:
        destination = PROCESSED_DIR / original_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        return Path(shutil.move(str(intake_path), str(destination)))

    @staticmethod
    def _move_original_to_failure(intake_path: Path, original_name: str) -> Path:
        destination = OUTPUT_FAILURE_DIR / original_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not intake_path.exists():
            return destination
        if destination.exists():
            destination.unlink()
        moved = Path(shutil.move(str(intake_path), str(destination)))
        logger.info("File moved to failure: source=%s destination=%s", intake_path, moved)
        return moved

    @staticmethod
    def _write_error_log(original_name: str, failed_step: str, error: str) -> None:
        error_log_path = OUTPUT_FAILURE_DIR / f"{Path(original_name).stem}_error.json"
        payload = {
            "file": original_name,
            "failed_step": failed_step,
            "error": error,
        }
        error_log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
