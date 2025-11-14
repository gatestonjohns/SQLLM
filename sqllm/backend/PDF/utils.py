from __future__ import annotations

from pathlib import Path
import pymupdf

AVERAGE_NUM_CHARS_PER_PAGE_EXPECTATION = 500


class PDFRequiresOCRError(RuntimeError):
    """Raised when a PDF cannot be processed."""


def _open_pdf(pdf_path: str) -> pymupdf.Document:
    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    return pymupdf.open(str(path))


def _check_readability(full_text: str, num_pages: int):
    if len(full_text) < (AVERAGE_NUM_CHARS_PER_PAGE_EXPECTATION * num_pages):
        raise PDFRequiresOCRError(
            f"PDF averages less than {AVERAGE_NUM_CHARS_PER_PAGE_EXPECTATION} characters per page, this PDF may require OCR processing."
        )


def extract_full_pdf_text(
    pdf_path: str, page_break_marker: str = "\n------page break------\n"
) -> str:
    """Return the full text of a PDF as a single string with page break markers.

    Args:
        pdf_path: The path to the PDF file.
        page_break_marker: The marker to use to separate pages in concatenated text result.

    Returns:
        The full text of the PDF as a single string with page break markers.
    """
    doc = _open_pdf(pdf_path)

    page_texts = [page.get_text("text") for page in doc]

    full_text = page_break_marker.join(page_texts)

    _check_readability(full_text, len(doc))

    return full_text
