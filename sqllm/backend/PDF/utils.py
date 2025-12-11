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
    """
    Check if the PDF is readable by ensuring it has at least the average number of characters per page.

    Args:
        full_text: The full text of the PDF.
        num_pages: The number of pages in the PDF.

    Raises:
        PDFRequiresOCRError: If the PDF has less than the average number of characters per page.
    """
    if len(full_text) < (AVERAGE_NUM_CHARS_PER_PAGE_EXPECTATION * num_pages):
        raise PDFRequiresOCRError(
            f"PDF averages less than {AVERAGE_NUM_CHARS_PER_PAGE_EXPECTATION} characters per page, this PDF may require OCR processing."
        )


def extract_pdf_page_text_list(pdf_path: str) -> list[str]:
    """
    Return the text of all pages of a PDF as a list of strings (one for each page).

    Args:
        pdf_path: The path to the PDF file.

    Returns:
        The text of all pages of the PDF as a list of strings (one for each page).
    """
    doc = _open_pdf(pdf_path)

    page_texts = [page.get_text("text") for page in doc]

    _check_readability("\n".join(page_texts), len(doc))

    return page_texts


def extract_full_pdf_text(pdf_path: str, page_break_delimiter: str) -> str:
    """
    Return the full text of a PDF as a single string with page break delimiters.

    Args:
        pdf_path: The path to the PDF file.
        page_break_delimiter: The delimiter to use to separate pages in concatenated text result.

    Returns:
        The full text of the PDF as a single string with page break delimiters.
    """
    return page_break_delimiter.join(extract_pdf_page_text_list(pdf_path))


def get_page_annotated_text(
    pdf_path: str,
    start_page: int | None = None,
    end_page: int | None = None,
) -> str:
    """
    Return the text of a subset of pages of a PDF as a single string with page number annotations.

    Args:
        pdf_path: The path to the PDF file.
        start_page: The page number to start from.
        end_page: The page number to end at.

    Returns:
        The text of the subset of pages of the PDF as a single string with page number annotations.
    """
    page_texts = extract_pdf_page_text_list(pdf_path)

    start_page = start_page or 1
    end_page = end_page or len(page_texts)

    sliced_page_texts = page_texts[start_page - 1 : end_page]

    return "\n".join(
        [
            f"[START OF PAGE {i + start_page}]\n{page}\n[END OF PAGE {i + start_page}]"
            for i, page in enumerate(sliced_page_texts)
        ]
    )
