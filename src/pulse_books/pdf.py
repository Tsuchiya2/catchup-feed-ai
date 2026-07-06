"""PDF text extraction (§6): pypdf, page by page.

Extraction-quality limits (code blocks losing indentation, headers/footers
bleeding into the text, hyphenation) are accepted by design — pages that
extract poorly get a warning log, never an error. Only a PDF that yields
no text at all (image-only scan, encrypted/DRM file — C-15 forbids those
anyway) aborts the ingest.
"""

from pathlib import Path

import structlog
from pypdf import PdfReader

from pulse_books.errors import PdfExtractionError

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)


def extract_text(pdf_path: Path) -> str:
    """Extract the full text of a PDF, pages joined by blank lines.

    The page join ("\\n\\n") doubles as a paragraph boundary for the
    chunker's PARAGRAPH strategy.
    """
    if not pdf_path.is_file():
        raise PdfExtractionError(f"PDF not found: {pdf_path}")

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        raise PdfExtractionError(f"failed to open PDF {pdf_path}: {exc}") from exc

    if reader.is_encrypted:
        # DRM'd / password-protected books are out of scope (C-15).
        raise PdfExtractionError(f"PDF is encrypted, cannot ingest (C-15): {pdf_path}")

    page_texts: list[str] = []
    empty_pages = 0
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception as exc:
            logger.warning("pdf: page extraction failed", page=page_number, error=str(exc))
            text = ""
        if text:
            page_texts.append(text)
        else:
            empty_pages += 1

    total_pages = len(reader.pages)
    if empty_pages:
        logger.warning(
            "pdf: some pages produced no text (image page or extraction limit)",
            empty_pages=empty_pages,
            total_pages=total_pages,
        )

    combined = "\n\n".join(page_texts)
    if not combined:
        raise PdfExtractionError(
            f"no text could be extracted from {pdf_path} "
            f"({total_pages} pages; image-only scan?)"
        )

    logger.info(
        "pdf: text extracted",
        pages=total_pages,
        characters=len(combined),
    )
    return combined
