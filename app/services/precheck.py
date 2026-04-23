from __future__ import annotations

from pathlib import Path

from PyPDF2 import PdfReader

from app.core.config import settings

PRECHECK_MESSAGES: dict[str, str] = {
    "PASSWORD": "Password-protected PDF not supported",
    "XFA": "XFA forms not supported. Please flatten PDF",
    "SIZE": "File too large. Please upload smaller file",
    "TABLE": "Unsupported table structure detected in PDF",
}


def _max_pdf_size_bytes() -> int:
    mb = int(getattr(settings, "MAX_PDF_SIZE_MB", 25))
    return max(1, mb) * 1024 * 1024


def _fail(check_type: str, reason: str) -> dict[str, str | bool]:
    return {
        "valid": False,
        "reason": reason,
        "type": check_type,
    }


def validate_pdf(file_path: str | Path) -> dict[str, str | bool]:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return _fail("TABLE", "Input PDF not found.")

    if path.stat().st_size > _max_pdf_size_bytes():
        return _fail("SIZE", PRECHECK_MESSAGES["SIZE"])

    raw = path.read_bytes()
    if b"/XFA" in raw:
        return _fail("XFA", PRECHECK_MESSAGES["XFA"])

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            return _fail("PASSWORD", PRECHECK_MESSAGES["PASSWORD"])
    except Exception:
        # Keep a stable type/reason for pre-Adobe validation failures.
        return _fail("TABLE", PRECHECK_MESSAGES["TABLE"])

    return {
        "valid": True,
        "reason": "",
        "type": "",
    }
