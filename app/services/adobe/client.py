# pyright: reportMissingImports=false
import asyncio
import logging
import os
from pathlib import Path

from adobe.pdfservices.operation.auth.service_principal_credentials import (
    ServicePrincipalCredentials,
)
from adobe.pdfservices.operation.exception.exceptions import (
    SdkException,
    ServiceApiException,
    ServiceUsageException,
)
from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
from adobe.pdfservices.operation.io.stream_asset import StreamAsset
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.autotag_pdf_job import AutotagPDFJob
from adobe.pdfservices.operation.pdfjobs.jobs.create_pdf_job import CreatePDFJob
from adobe.pdfservices.operation.pdfjobs.jobs.pdf_accessibility_checker_job import (
    PDFAccessibilityCheckerJob,
)
from adobe.pdfservices.operation.pdfjobs.params.autotag_pdf.autotag_pdf_params import (
    AutotagPDFParams,
)
from adobe.pdfservices.operation.pdfjobs.result.autotag_pdf_result import AutotagPDFResult
from adobe.pdfservices.operation.pdfjobs.result.create_pdf_result import CreatePDFResult
from adobe.pdfservices.operation.pdfjobs.result.pdf_accessibility_checker_result import (
    PDFAccessibilityCheckerResult,
)
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class AdobeAPIError(Exception):
    pass


class AdobeClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        logger.info("Adobe client initialization started")
        self._load_env_if_needed()
        self.client_id = client_id or os.getenv("ADOBE_CLIENT_ID") or os.getenv("PDF_SERVICES_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("ADOBE_CLIENT_SECRET") or os.getenv("PDF_SERVICES_CLIENT_SECRET")

        if not self.client_id or not self.client_secret:
            raise AdobeAPIError(
                "Adobe credentials are missing. Set ADOBE_CLIENT_ID/ADOBE_CLIENT_SECRET "
                "or PDF_SERVICES_CLIENT_ID/PDF_SERVICES_CLIENT_SECRET."
            )

        credentials = ServicePrincipalCredentials(
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        self._pdf_services = PDFServices(credentials=credentials)
        logger.info("Adobe client initialized successfully")

    @staticmethod
    def _load_env_if_needed() -> None:
        if (os.getenv("ADOBE_CLIENT_ID") and os.getenv("ADOBE_CLIENT_SECRET")) or (
            os.getenv("PDF_SERVICES_CLIENT_ID") and os.getenv("PDF_SERVICES_CLIENT_SECRET")
        ):
            return
        load_dotenv(dotenv_path=Path(".env"), override=False)
        logger.info("Environment loaded from .env for Adobe credentials")

    def upload_asset(self, file_path: str | Path) -> str:
        source = Path(file_path)
        logger.info("Adobe upload step started: path=%s", source)
        if not source.exists() or not source.is_file():
            raise AdobeAPIError(f"Input file does not exist: {source}")

        try:
            with source.open("rb") as file_obj:
                input_asset = self._pdf_services.upload(
                    input_stream=file_obj.read(),
                    mime_type=self._guess_media_type(source),
                )
        except (ServiceApiException, ServiceUsageException, SdkException, OSError) as exc:
            raise AdobeAPIError(f"Failed to upload asset: {source}") from exc

        asset_id = self._extract_asset_id(input_asset)
        logger.info("Adobe asset uploaded: asset_id=%s", asset_id)
        return asset_id

    def convert_to_pdf(self, input_path: str | Path, output_dir: str | Path | None = None) -> Path:
        source = Path(input_path)
        target_dir = Path(output_dir) if output_dir else source.parent
        output_path = target_dir / f"{source.stem}.converted.pdf"
        logger.info("Adobe convert_to_pdf started: input=%s output=%s", source, output_path)

        try:
            with source.open("rb") as file_obj:
                input_asset = self._pdf_services.upload(
                    input_stream=file_obj.read(),
                    mime_type=self._guess_media_type(source),
                )
            asset_id = self._extract_asset_id(input_asset)
            logger.info("Adobe asset uploaded: asset_id=%s", asset_id)

            create_pdf_job = CreatePDFJob(input_asset)
            location = self._pdf_services.submit(create_pdf_job)
            logger.info("Adobe job created: job_id=%s status=SUBMITTED", location)
            pdf_services_response = self._pdf_services.get_job_result(location, CreatePDFResult)

            result_asset: CloudAsset = pdf_services_response.get_result().get_asset()
            stream_asset: StreamAsset = self._pdf_services.get_content(result_asset)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("wb") as file_obj:
                file_obj.write(stream_asset.get_input_stream())
            logger.info("Adobe job status: job_id=%s status=DONE", location)
            logger.info("Adobe convert_to_pdf completed: output=%s", output_path)
        except (ServiceApiException, ServiceUsageException, SdkException, OSError) as exc:
            logger.exception("Adobe convert_to_pdf failed: input=%s", source)
            raise AdobeAPIError("Failed to convert file to PDF.") from exc
        return output_path

    def auto_tag(
        self,
        input_path: str | Path,
        output_dir: str | Path | None = None,
        report_dir: str | Path | None = None,
    ) -> tuple[Path, Path | None]:
        source = Path(input_path)
        target_output_dir = Path(output_dir) if output_dir else source.parent
        target_report_dir = Path(report_dir) if report_dir else source.parent
        tagged_output_path = target_output_dir / f"{source.stem}.tagged.pdf"
        report_path: Path | None = None
        logger.info("Adobe auto_tag started: input=%s tagged_output=%s", source, tagged_output_path)

        try:
            with source.open("rb") as file_obj:
                input_asset = self._pdf_services.upload(
                    input_stream=file_obj.read(),
                    mime_type=PDFServicesMediaType.PDF,
                )
            asset_id = self._extract_asset_id(input_asset)
            logger.info("Adobe asset uploaded: asset_id=%s", asset_id)

            params = AutotagPDFParams(generate_report=True, shift_headings=True)
            autotag_job = AutotagPDFJob(input_asset=input_asset, autotag_pdf_params=params)
            location = self._pdf_services.submit(autotag_job)
            logger.info("Adobe job created: job_id=%s status=SUBMITTED", location)
            pdf_services_response = self._pdf_services.get_job_result(location, AutotagPDFResult)

            result_asset: CloudAsset = pdf_services_response.get_result().get_tagged_pdf()
            stream_asset: StreamAsset = self._pdf_services.get_content(result_asset)
            tagged_output_path.parent.mkdir(parents=True, exist_ok=True)
            with tagged_output_path.open("wb") as file_obj:
                file_obj.write(stream_asset.get_input_stream())

            report_asset: CloudAsset | None = pdf_services_response.get_result().get_report()
            if report_asset:
                report_path = target_report_dir / f"{source.stem}.autotag-report.xlsx"
                stream_report = self._pdf_services.get_content(report_asset)
                report_path.parent.mkdir(parents=True, exist_ok=True)
                with report_path.open("wb") as file_obj:
                    file_obj.write(stream_report.get_input_stream())
                logger.info("Adobe auto_tag report generated: path=%s", report_path)
            logger.info("Adobe job status: job_id=%s status=DONE", location)
            logger.info("Adobe auto_tag completed: tagged_output=%s", tagged_output_path)
        except (ServiceApiException, ServiceUsageException, SdkException, OSError) as exc:
            logger.exception("Adobe auto_tag failed: input=%s", source)
            raise AdobeAPIError("Failed to auto-tag PDF.") from exc
        return tagged_output_path, report_path

    def check_accessibility(self, input_path: str | Path, report_dir: str | Path | None = None) -> Path:
        source = Path(input_path)
        target_report_dir = Path(report_dir) if report_dir else source.parent
        report_output_path = target_report_dir / f"{source.stem}.accessibility-report.json"
        logger.info("Adobe accessibility_check started: input=%s report_output=%s", source, report_output_path)
        try:
            with source.open("rb") as file_obj:
                input_asset = self._pdf_services.upload(
                    input_stream=file_obj.read(),
                    mime_type=PDFServicesMediaType.PDF,
                )
            asset_id = self._extract_asset_id(input_asset)
            logger.info("Adobe asset uploaded: asset_id=%s", asset_id)

            checker_job = PDFAccessibilityCheckerJob(input_asset=input_asset)
            location = self._pdf_services.submit(checker_job)
            logger.info("Adobe job created: job_id=%s status=SUBMITTED", location)
            pdf_services_response = self._pdf_services.get_job_result(
                location, PDFAccessibilityCheckerResult
            )

            report_asset: CloudAsset = pdf_services_response.get_result().get_report()
            report_stream: StreamAsset = self._pdf_services.get_content(report_asset)
            report_output_path.parent.mkdir(parents=True, exist_ok=True)
            with report_output_path.open("wb") as file_obj:
                file_obj.write(report_stream.get_input_stream())
            logger.info("Adobe job status: job_id=%s status=DONE", location)
            logger.info("Adobe accessibility_check completed: report=%s", report_output_path)
        except (ServiceApiException, ServiceUsageException, SdkException, OSError) as exc:
            logger.exception("Adobe accessibility_check failed: input=%s", source)
            raise AdobeAPIError("Failed to run accessibility check.") from exc
        return report_output_path

    async def convert_to_pdf_async(self, input_path: str | Path, output_dir: str | Path | None = None) -> Path:
        return await asyncio.to_thread(self.convert_to_pdf, input_path, output_dir)

    async def auto_tag_async(
        self,
        input_path: str | Path,
        output_dir: str | Path | None = None,
        report_dir: str | Path | None = None,
    ) -> tuple[Path, Path | None]:
        return await asyncio.to_thread(self.auto_tag, input_path, output_dir, report_dir)

    async def check_accessibility_async(self, input_path: str | Path, report_dir: str | Path | None = None) -> Path:
        return await asyncio.to_thread(self.check_accessibility, input_path, report_dir)

    @staticmethod
    def _guess_media_type(path: Path) -> PDFServicesMediaType:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return PDFServicesMediaType.PDF
        if suffix == ".docx":
            return PDFServicesMediaType.DOCX
        if suffix == ".doc":
            return PDFServicesMediaType.DOC
        if suffix == ".pptx":
            return PDFServicesMediaType.PPTX
        if suffix == ".xlsx":
            return PDFServicesMediaType.XLSX
        if suffix == ".txt":
            return PDFServicesMediaType.TXT
        raise AdobeAPIError(f"Unsupported file type for Adobe upload: {path.suffix}")

    @staticmethod
    def _extract_asset_id(asset: CloudAsset) -> str:
        for attr in ("asset_id", "assetId", "assetID"):
            if hasattr(asset, attr):
                value = getattr(asset, attr)
                if callable(value):
                    value = value()
                if value:
                    return str(value)
        as_dict = asset.__dict__ if hasattr(asset, "__dict__") else {}
        for key in ("asset_id", "assetId", "assetID"):
            if as_dict.get(key):
                return str(as_dict[key])
        return "unknown"
