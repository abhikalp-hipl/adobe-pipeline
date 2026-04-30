from __future__ import annotations

import asyncio
from pathlib import Path

from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

from app.core.config import settings

PRECHECK_MESSAGES: dict[str, str] = {
    "PASSWORD": "Password-protected PDF not supported",
    "XFA": "XFA forms not supported. Please flatten PDF",
    "SIZE": "File too large. Please upload smaller file",
    "TABLE": "Unsupported table structure detected in PDF",
    "NOT_FOUND": "Input PDF not found.",
    "PARSE": "Unable to parse PDF. The file may be corrupted or unsupported.",
    "READ": "Unable to read PDF file from disk.",
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
        return _fail("NOT_FOUND", PRECHECK_MESSAGES["NOT_FOUND"])

    if path.stat().st_size > _max_pdf_size_bytes():
        return _fail("SIZE", PRECHECK_MESSAGES["SIZE"])

    try:
        raw = path.read_bytes()
    except OSError:
        return _fail("READ", PRECHECK_MESSAGES["READ"])
    if b"/XFA" in raw:
        return _fail("XFA", PRECHECK_MESSAGES["XFA"])

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            return _fail("PASSWORD", PRECHECK_MESSAGES["PASSWORD"])
    except PdfReadError:
        return _fail("PARSE", PRECHECK_MESSAGES["PARSE"])
    except OSError:
        return _fail("READ", PRECHECK_MESSAGES["READ"])
    except Exception:
        # Keep a stable fallback for unknown pre-Adobe parser failures.
        return _fail("PARSE", PRECHECK_MESSAGES["PARSE"])

    return {
        "valid": True,
        "reason": "",
        "type": "",
    }


async def validate_pdf_async(file_path: str | Path) -> dict[str, str | bool]:
    return await asyncio.to_thread(validate_pdf, file_path)
