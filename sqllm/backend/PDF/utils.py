from __future__ import annotations

from pathlib import Path
import pymupdf
import logging

AVERAGE_NUM_CHARS_PER_PAGE_EXPECTATION = 500


class PDFRequiresOCRError(RuntimeError):
    """Raised when a PDF cannot be processed."""


def _open_pdf(pdf_path: str) -> pymupdf.Document:
    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    return pymupdf.open(str(path))


def extract_full_pdf_text(
    pdf_path: str, page_break_marker: str = "\n------page break------\n"
) -> str:
    """Return the full text of a PDF as a single string with page break markers."""
    doc = _open_pdf(pdf_path)
    text = ""

    for page in doc:
        text += page.get_text("text")
        text += page_break_marker

    if len(text) < (AVERAGE_NUM_CHARS_PER_PAGE_EXPECTATION * len(doc)):
        logging.warning(
            f"PDF {pdf_path} averages less than {AVERAGE_NUM_CHARS_PER_PAGE_EXPECTATION} characters per page, this PDF may require OCR processing."
        )
        raise PDFRequiresOCRError(
            f"PDF {pdf_path} averages less than {AVERAGE_NUM_CHARS_PER_PAGE_EXPECTATION} characters per page, this PDF may require OCR processing."
        )

    return text
