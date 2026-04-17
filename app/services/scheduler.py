import logging
import threading
import uuid
import json
import hashlib
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from datetime import datetime, UTC
from datetime import timedelta

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import Document, DocumentStatus, UserToken
from app.services.auth.microsoft_auth import MicrosoftAuthError, MicrosoftAuthService
from app.services.email_service import EmailServiceError, send_email
from app.services.email_templates import build_pipeline_email
from app.services.orchestrator import Orchestrator, OrchestratorError
from app.services.storage.onedrive import (
    INTAKE_FOLDER,
    PROCESSED_FOLDER,
    OUTPUT_SUCCESS_FOLDER,
    OUTPUT_FAILURE_FOLDER,
    OneDriveClient,
    OneDriveError,
    OneDriveNotFoundError,
)

logger = logging.getLogger(__name__)

INTAKE_DIR = Path("storage/intake")
PROCESSED_DIR = Path("storage/processed")
IGNORED_SUFFIXES = {".tmp", ".part", ".swp"}
ALLOWED_INPUT_EXTENSIONS = {".pdf", ".doc", ".docx"}
DENIED_EXTENSIONS = {".xlsx", ".json", ".html"}
GENERATED_MARKERS = (".converted", ".tagged", "report")


class Scheduler:
    def __init__(self, interval: int | None = None) -> None:
        configured_interval = interval or settings.SCHEDULER_INTERVAL_SECONDS
        self.interval = max(1, configured_interval)
        self.max_files_per_cycle = max(1, settings.MAX_FILES_PER_CYCLE)
        self.processing_delay_seconds = max(0, settings.PROCESSING_DELAY_SECONDS)
        self.storage_provider = settings.STORAGE_PROVIDER
        self.automation_enabled = True
        self.auth_service = MicrosoftAuthService() if self.storage_provider == "onedrive" else None
        self.onedrive_client = OneDriveClient() if self.storage_provider == "onedrive" else None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._wakeup_event = threading.Event()
        self.last_failure: dict | None = None

    def _record_failure(self, *, filename: str, failed_step: str, error: str, progress: int) -> None:
        self.last_failure = {
            "at": datetime.now(UTC),
            "current_file": filename,
            "failed_step": failed_step,
            "error": error,
            "progress": progress,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.info("Scheduler already running")
            return

        INTAKE_DIR.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="document-scheduler", daemon=True)
        self._thread.start()
        logger.info(
            "Scheduler started: interval=%s seconds storage_provider=%s",
            self.interval,
            self.storage_provider,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Scheduler stopped")

    def status(self) -> str:
        if self._thread and self._thread.is_alive():
            return "running"
        return "stopped"

    def update_interval(self, new_interval: int) -> None:
        self.interval = max(1, new_interval)
        logger.info("Scheduler interval updated: interval=%s seconds", self.interval)
        # Wake the scheduler loop so the new interval takes effect immediately.
        self._wakeup_event.set()

    def run_once(self) -> None:
        run_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)
        logger.info("Manual scheduler run started: run_id=%s", run_id)

        files_summary: list[dict[str, str]] = []
        access_passed = 0
        access_failed = 0
        access_manual = 0

        try:
            if self.storage_provider == "onedrive":
                run_result = self.process_onedrive_intake()
                files_summary = run_result.get("files", [])
                access = run_result.get("accessibility", {})
                access_passed = int(access.get("passed", 0))
                access_failed = int(access.get("failed", 0))
                access_manual = int(access.get("manual", 0))
            else:
                run_result = self._poll_local_intake_folder()
                files_summary = run_result.get("files", [])
                access = run_result.get("accessibility", {})
                access_passed = int(access.get("passed", 0))
                access_failed = int(access.get("failed", 0))
                access_manual = int(access.get("manual", 0))
        finally:
            finished_at = datetime.now(UTC)
            duration = self._format_duration(finished_at - started_at)
            total_files = len(files_summary)
            success_count = sum(1 for item in files_summary if item.get("status") == DocumentStatus.COMPLETED.value)
            failure_count = sum(1 for item in files_summary if item.get("status") == DocumentStatus.FAILED.value)

            run_data = {
                "run_id": run_id,
                "duration": duration,
                "total_files": total_files,
                "success_count": success_count,
                "failure_count": failure_count,
                "files": files_summary,
                "passed": access_passed,
                "failed": access_failed,
                "manual": access_manual,
                "dashboard_url": settings.FRONTEND_DASHBOARD_URL,
            }

            try:
                to_email = self._get_latest_user_email()
                if not to_email:
                    logger.info("Skipping email notification (no user email found): run_id=%s", run_id)
                else:
                    if failure_count == 0:
                        subject = f"✅ Pipeline Completed | {total_files} Files"
                    else:
                        subject = f"❌ Pipeline Completed with Errors | {failure_count} Failed"
                    html_content = build_pipeline_email(run_data)
                    send_email(to_email=to_email, subject=subject, html_content=html_content)
                    logger.info("Pipeline summary email sent: run_id=%s to=%s", run_id, to_email)
            except EmailServiceError:
                logger.exception("Email notification failed: run_id=%s", run_id)
            except Exception:
                logger.exception("Unexpected error while sending email: run_id=%s", run_id)

            logger.info("Manual scheduler run finished: run_id=%s duration=%s", run_id, duration)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            logger.info("Scheduler polling cycle started")
            try:
                self.run_once()
            except Exception:
                logger.exception("Scheduler polling cycle failed")
            logger.info("Scheduler polling cycle ended")
            self._wakeup_event.wait(self.interval)
            self._wakeup_event.clear()

    def _poll_local_intake_folder(self) -> dict:
        candidate_files: list[Path] = []
        for path in sorted(INTAKE_DIR.iterdir(), key=lambda item: item.name.lower()):
            is_processible, reason = self._is_processible_file(path)
            if is_processible:
                candidate_files.append(path)
                continue

            if reason == "generated":
                logger.info("Scheduler skipped generated file: filename=%s", path.name)
            elif reason == "invalid":
                logger.info("Scheduler skipped invalid file: filename=%s", path.name)

        process_batch = candidate_files[: self.max_files_per_cycle]
        logger.info(
            "Scheduler batch prepared: candidates=%d processing_now=%d deferred=%d max_per_cycle=%d",
            len(candidate_files),
            len(process_batch),
            max(0, len(candidate_files) - len(process_batch)),
            self.max_files_per_cycle,
        )

        files_summary: list[dict[str, str]] = []
        access_passed = 0
        access_failed = 0
        access_manual = 0

        for index, file_path in enumerate(process_batch):
            result = self._register_and_trigger(file_path=file_path, source_id=None)
            if result:
                files_summary.append(
                    {
                        "name": result.get("name", ""),
                        "status": result.get("status", ""),
                        "error": result.get("error", ""),
                    }
                )
                report_path = result.get("report_path")
                if report_path:
                    summary = self._read_accessibility_summary(report_path)
                    access_passed += int(summary.get("passed", 0))
                    access_failed += int(summary.get("failed", 0))
                    access_manual += int(summary.get("manual", 0))
            if index < len(process_batch) - 1 and self.processing_delay_seconds > 0:
                self._stop_event.wait(self.processing_delay_seconds)

        return {
            "files": files_summary,
            "accessibility": {"passed": access_passed, "failed": access_failed, "manual": access_manual},
        }

    def process_onedrive_intake(self) -> dict:
        if not self.onedrive_client:
            raise OneDriveError("OneDrive client is not initialized.")
        if not self.auth_service:
            raise MicrosoftAuthError("Microsoft auth service is not initialized.")

        try:
            all_files = self.onedrive_client.list_files(
                access_token=self._get_onedrive_access_token(),
                folder_path=INTAKE_FOLDER,
            )
        except (OneDriveError, MicrosoftAuthError):
            logger.exception("Scheduler failed to list OneDrive intake folder: folder=%s", INTAKE_FOLDER)
            raise

        candidate_files: list[dict[str, str]] = []
        for remote_file in sorted(all_files, key=lambda item: item["name"].lower()):
            filename = Path(remote_file["name"]).name
            is_processible, reason = self._is_processible_filename(filename)
            if is_processible:
                candidate_files.append(remote_file)
                continue
            if reason == "generated":
                logger.info("Scheduler skipped generated OneDrive file: filename=%s file_id=%s", filename, remote_file["id"])
            elif reason == "invalid":
                logger.info("Scheduler skipped invalid OneDrive file: filename=%s file_id=%s", filename, remote_file["id"])

        # Apply max_files_per_cycle to files that are not already known in DB,
        # so previously processed files do not consume the current run capacity.
        db = SessionLocal()
        try:
            candidate_source_ids = [item["id"] for item in candidate_files]
            existing_source_ids: set[str] = set()
            if candidate_source_ids:
                existing_rows = (
                    db.query(Document.filename)
                    .filter(Document.filename.in_(candidate_source_ids))
                    .all()
                )
                existing_source_ids = {row[0] for row in existing_rows}
        finally:
            db.close()

        process_batch = []
        for remote_file in candidate_files:
            if remote_file["id"] in existing_source_ids:
                continue
            process_batch.append(remote_file)
            if len(process_batch) >= self.max_files_per_cycle:
                break
        logger.info(
            "OneDrive intake batch prepared: candidates=%d unprocessed=%d processing_now=%d deferred=%d max_per_cycle=%d",
            len(candidate_files),
            max(0, len(candidate_files) - len(existing_source_ids)),
            len(process_batch),
            max(0, len(candidate_files) - len(existing_source_ids) - len(process_batch)),
            self.max_files_per_cycle,
        )

        processed_count = 0
        skipped_count = len(candidate_files) - len(process_batch)
        failed_count = 0
        files_summary: list[dict[str, str]] = []
        access_passed = 0
        access_failed = 0
        access_manual = 0
        for index, remote_file in enumerate(process_batch):
            file_id = remote_file["id"]
            filename = Path(remote_file["name"]).name
            local_path = INTAKE_DIR / f"{file_id}_{filename}"
            try:
                self.onedrive_client.download_file(
                    access_token=self._get_onedrive_access_token(),
                    file_id=file_id,
                    local_path=local_path,
                )
                logger.info("File fetched from OneDrive: file_id=%s filename=%s local_path=%s", file_id, filename, local_path)
                result = self._register_and_trigger_onedrive(
                    file_path=local_path,
                    source_id=file_id,
                    original_filename=filename,
                )
                if result:
                    processed_count += 1
                    files_summary.append(
                        {
                            "name": result.get("name", ""),
                            "status": result.get("status", ""),
                            "error": result.get("error", ""),
                        }
                    )
                    report_path = result.get("report_path")
                    if report_path:
                        summary = self._read_accessibility_summary(report_path)
                        access_passed += int(summary.get("passed", 0))
                        access_failed += int(summary.get("failed", 0))
                        access_manual += int(summary.get("manual", 0))
                else:
                    skipped_count += 1
            except OneDriveNotFoundError:
                failed_count += 1
                logger.error("OneDrive file no longer exists: file_id=%s filename=%s", file_id, filename)
                files_summary.append({"name": filename, "status": DocumentStatus.FAILED.value, "error": "OneDrive file no longer exists"})
            except OneDriveError:
                failed_count += 1
                logger.exception("Failed to download/process OneDrive file: file_id=%s filename=%s", file_id, filename)
                files_summary.append({"name": filename, "status": DocumentStatus.FAILED.value, "error": "Failed to download/process OneDrive file"})
            finally:
                try:
                    local_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Failed to clean up downloaded OneDrive file: path=%s", local_path)

            if index < len(process_batch) - 1 and self.processing_delay_seconds > 0:
                self._stop_event.wait(self.processing_delay_seconds)

        return {
            "processed": processed_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "files": files_summary,
            "accessibility": {"passed": access_passed, "failed": access_failed, "manual": access_manual},
        }

    def _register_and_trigger(
        self,
        file_path: Path,
        source_id: str | None,
        original_filename: str | None = None,
    ) -> dict[str, str] | None:
        display_filename = original_filename or file_path.name
        filename = file_path.name
        logger.info("Scheduler evaluating file: filename=%s source_id=%s", display_filename, source_id or "n/a")
        db = SessionLocal()
        try:
            dedupe_key = source_id or filename
            if not source_id and self._is_duplicate_local_file(file_path):
                logger.info("Scheduler skipping duplicate local file: filename=%s", display_filename)
                return {
                    "name": display_filename,
                    "status": "SKIPPED",
                    "error": "Already exists in processed archive.",
                    "report_path": "",
                }
            existing = db.query(Document).filter(Document.filename == dedupe_key).first()
            if existing:
                if existing.status == DocumentStatus.FAILED:
                    logger.info(
                        "Scheduler skipping recently failed file: filename=%s source_id=%s document_id=%s",
                        display_filename,
                        source_id or "n/a",
                        existing.id,
                    )
                else:
                    logger.info(
                        "Scheduler skipping known file: filename=%s source_id=%s document_id=%s",
                        display_filename,
                        source_id or "n/a",
                        existing.id,
                    )
                return {
                    "name": display_filename,
                    "status": existing.status.value,
                    "error": "Already processed.",
                    "report_path": "",
                }

            document = Document(filename=dedupe_key, status=DocumentStatus.UPLOADED)
            db.add(document)
            db.commit()
            db.refresh(document)
            logger.info(
                "Scheduler created document: document_id=%s dedupe_key=%s source_file=%s",
                document.id,
                dedupe_key,
                display_filename,
            )

            orchestrator = Orchestrator(db=db)
            result = orchestrator.process_document(document_id=document.id, input_path=file_path)

            if self.storage_provider == "onedrive":
                try:
                    self._upload_onedrive_outputs(
                        tagged_pdf_path=result["tagged_pdf_path"],
                        report_path=result["report_path"],
                        autotag_report_path=result.get("autotag_report_path"),
                    )
                except OneDriveError:
                    document.status = DocumentStatus.FAILED
                    db.add(document)
                    db.commit()
                    logger.exception("Scheduler failed to upload outputs to OneDrive: document_id=%s", document.id)
                    return {
                        "name": display_filename,
                        "status": DocumentStatus.FAILED.value,
                        "error": "Failed to upload outputs to OneDrive.",
                        "report_path": result.get("report_path", ""),
                    }
            logger.info("Scheduler triggered processing: document_id=%s", document.id)
            return {
                "name": display_filename,
                "status": DocumentStatus.COMPLETED.value,
                "error": "",
                "report_path": result.get("report_path", ""),
            }
        except IntegrityError:
            db.rollback()
            logger.info("Scheduler encountered duplicate file insert: filename=%s", display_filename)
            return {"name": display_filename, "status": "SKIPPED", "error": "Duplicate insert ignored.", "report_path": ""}
        except OrchestratorError as exc:
            logger.exception("Scheduler processing failed for file: filename=%s", display_filename)
            failed_step = getattr(exc, "failed_step", "") or "unknown"
            progress_map = {"fetch": 5, "convert_to_pdf": 30, "auto_tag": 60, "check_accessibility": 80}
            self._record_failure(
                filename=display_filename,
                failed_step=failed_step,
                error=str(exc) or "Pipeline failed.",
                progress=int(progress_map.get(failed_step, 40)),
            )
            return {
                "name": display_filename,
                "status": DocumentStatus.FAILED.value,
                "error": str(exc) or "Pipeline failed.",
                "report_path": "",
            }
        except Exception:
            logger.exception("Scheduler failed while handling file: filename=%s", display_filename)
            return {
                "name": display_filename,
                "status": DocumentStatus.FAILED.value,
                "error": "Scheduler failed while handling file.",
                "report_path": "",
            }
        finally:
            db.close()

    def _register_and_trigger_onedrive(
        self,
        file_path: Path,
        source_id: str,
        original_filename: str,
    ) -> dict[str, str] | None:
        db = SessionLocal()
        document: Document | None = None
        try:
            existing = db.query(Document).filter(Document.filename == source_id).first()
            if existing:
                logger.info(
                    "Skipping already processed OneDrive file: source_id=%s filename=%s document_id=%s",
                    source_id,
                    original_filename,
                    existing.id,
                )
                return {
                    "name": original_filename,
                    "status": existing.status.value,
                    "error": "Already processed.",
                    "report_path": "",
                }

            document = Document(filename=source_id, status=DocumentStatus.UPLOADED)
            db.add(document)
            db.commit()
            db.refresh(document)
            logger.info(
                "Created document for OneDrive file: document_id=%s source_id=%s filename=%s",
                document.id,
                source_id,
                original_filename,
            )

            orchestrator = Orchestrator(db=db)
            result = orchestrator.process_document(document_id=document.id, input_path=file_path)
            self.onedrive_client.move_file(
                access_token=self._get_onedrive_access_token(),
                file_id=source_id,
                folder_path=PROCESSED_FOLDER,
                filename=original_filename,
            )
            logger.info("OneDrive original moved to processed: file_id=%s filename=%s", source_id, original_filename)
            self._upload_onedrive_outputs(
                tagged_pdf_path=result["tagged_pdf_path"],
                report_path=result["report_path"],
                autotag_report_path=result.get("autotag_report_path"),
            )
            logger.info("Processed OneDrive file successfully: source_id=%s document_id=%s", source_id, document.id)
            return {
                "name": original_filename,
                "status": DocumentStatus.COMPLETED.value,
                "error": "",
                "report_path": result.get("report_path", ""),
            }
        except IntegrityError:
            db.rollback()
            logger.info("Duplicate OneDrive document insert ignored: source_id=%s", source_id)
            return {"name": original_filename, "status": "SKIPPED", "error": "Duplicate insert ignored.", "report_path": ""}
        except OrchestratorError as exc:
            logger.exception("Processing failed for OneDrive file: source_id=%s filename=%s", source_id, original_filename)
            try:
                self.onedrive_client.move_file(
                    access_token=self._get_onedrive_access_token(),
                    file_id=source_id,
                    folder_path=OUTPUT_FAILURE_FOLDER,
                    filename=original_filename,
                )
                logger.info("OneDrive original moved to failure: file_id=%s filename=%s", source_id, original_filename)
            except OneDriveError:
                logger.exception("Failed to move OneDrive original to failure: file_id=%s", source_id)
            failed_step = getattr(exc, "failed_step", "") or "unknown"
            progress_map = {"fetch": 5, "convert_to_pdf": 30, "auto_tag": 60, "check_accessibility": 80}
            self._record_failure(
                filename=original_filename,
                failed_step=failed_step,
                error=str(exc) or "Pipeline failed.",
                progress=int(progress_map.get(failed_step, 40)),
            )
            return {
                "name": original_filename,
                "status": DocumentStatus.FAILED.value,
                "error": str(exc) or "Pipeline failed.",
                "report_path": "",
            }
        except OneDriveError:
            if document:
                document.status = DocumentStatus.FAILED
                db.add(document)
                db.commit()
            logger.exception("Upload failed for OneDrive outputs: source_id=%s document_id=%s", source_id, document.id if document else "n/a")
            return {
                "name": original_filename,
                "status": DocumentStatus.FAILED.value,
                "error": "Upload failed for OneDrive outputs.",
                "report_path": "",
            }
        finally:
            db.close()

    @staticmethod
    def _format_duration(delta: timedelta) -> str:
        seconds = int(max(0, delta.total_seconds()))
        if seconds < 60:
            return f"{seconds}s"
        minutes, sec = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes}m {sec}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m {sec}s"

    @staticmethod
    def _read_accessibility_summary(report_path: str) -> dict[str, int]:
        try:
            path = Path(report_path)
            if not path.exists():
                return {"passed": 0, "failed": 0, "manual": 0}
            raw = path.read_text(encoding="utf-8", errors="replace")
            payload = json.loads(raw)
            summary = payload.get("Summary") or {}
            passed = int(summary.get("Passed", 0)) + int(summary.get("Passed manually", 0))
            failed = int(summary.get("Failed", 0)) + int(summary.get("Failed manually", 0))
            manual = int(summary.get("Needs manual check", 0))
            return {"passed": passed, "failed": failed, "manual": manual}
        except Exception:
            logger.exception("Failed to parse accessibility report summary: path=%s", report_path)
            return {"passed": 0, "failed": 0, "manual": 0}

    @staticmethod
    def _get_latest_user_email() -> str:
        db = SessionLocal()
        try:
            token_row = db.query(UserToken).order_by(UserToken.updated_at.desc()).first()
            if not token_row or not token_row.user_email:
                return ""
            return token_row.user_email
        except Exception:
            logger.exception("Failed to resolve notification email address")
            return ""
        finally:
            db.close()

    def _upload_onedrive_outputs(
        self,
        tagged_pdf_path: str,
        report_path: str,
        autotag_report_path: str | None = None,
    ) -> None:
        if not self.onedrive_client:
            raise OneDriveError("OneDrive client is not initialized for upload.")

        tagged_path_obj = Path(tagged_pdf_path)
        report_path_obj = Path(report_path)
        self.onedrive_client.upload_file(
            access_token=self._get_onedrive_access_token(),
            local_path=tagged_path_obj,
            folder_path=OUTPUT_SUCCESS_FOLDER,
            filename=tagged_path_obj.name,
        )
        logger.info("Upload success to OneDrive: local=%s target_folder=%s", tagged_path_obj, OUTPUT_SUCCESS_FOLDER)
        self.onedrive_client.upload_file(
            access_token=self._get_onedrive_access_token(),
            local_path=report_path_obj,
            folder_path=OUTPUT_SUCCESS_FOLDER,
            filename=report_path_obj.name,
        )
        logger.info("Upload success to OneDrive: local=%s target_folder=%s", report_path_obj, OUTPUT_SUCCESS_FOLDER)
        if autotag_report_path:
            autotag_report_obj = Path(autotag_report_path)
            if autotag_report_obj.exists():
                self.onedrive_client.upload_file(
                    access_token=self._get_onedrive_access_token(),
                    local_path=autotag_report_obj,
                    folder_path=OUTPUT_SUCCESS_FOLDER,
                    filename=autotag_report_obj.name,
                )
                logger.info("Upload success to OneDrive: local=%s target_folder=%s", autotag_report_obj, OUTPUT_SUCCESS_FOLDER)

    def _get_onedrive_access_token(self) -> str:
        if not self.auth_service:
            raise MicrosoftAuthError("Microsoft auth service is not initialized.")
        db = SessionLocal()
        try:
            return self.auth_service.get_valid_access_token(db=db)
        finally:
            db.close()

    @staticmethod
    def _is_processible_file(path: Path) -> tuple[bool, str]:
        if not path.is_file():
            return False, "ignore"
        return Scheduler._is_processible_filename(path.name)

    @staticmethod
    def _is_processible_filename(name: str) -> tuple[bool, str]:
        if name.startswith(".") or name.startswith("~"):
            return False, "ignore"
        if Path(name).suffix.lower() in IGNORED_SUFFIXES:
            return False, "ignore"

        lower_name = name.lower()
        if any(marker in lower_name for marker in GENERATED_MARKERS):
            return False, "generated"

        suffix = Path(name).suffix.lower()
        if suffix in DENIED_EXTENSIONS:
            return False, "invalid"
        if suffix not in ALLOWED_INPUT_EXTENSIONS:
            return False, "invalid"
        return True, "valid"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def _is_duplicate_local_file(self, file_path: Path) -> bool:
        candidate_name = file_path.name
        existing_by_name = PROCESSED_DIR / candidate_name
        if existing_by_name.exists():
            return True
        if not PROCESSED_DIR.exists():
            return False
        candidate_hash = self._sha256(file_path)
        for processed_file in PROCESSED_DIR.iterdir():
            if not processed_file.is_file():
                continue
            try:
                if self._sha256(processed_file) == candidate_hash:
                    return True
            except OSError:
                logger.warning("Unable to hash processed file for dedupe: path=%s", processed_file)
        return False
