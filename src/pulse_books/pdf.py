"""PDF text extraction (§6): PyMuPDF (pymupdf), page by page.

PyMuPDF replaced pypdf after real-book validation: Japanese books with
embedded fonts came out 80–98% garbled through pypdf (unresolved
CID→Unicode mappings, "ͭ͘…"-style text), while PyMuPDF extracted the same
pages cleanly. PyMuPDF is AGPL-3.0 — this repository is itself published
under AGPL-3.0 to comply (see LICENSE / README).

Encryption policy (C-15, refined): C-15 exists to keep DRM'd books out.
Commercial DRM-free PDFs are often encrypted with an *owner* password only
(no password needed to read); those are legitimate and must ingest. So we
try the empty password and reject only PDFs that actually require a real
password to open.

Extraction-quality limits (code blocks losing indentation, headers/footers
bleeding into the text, hyphenation) are accepted by design — pages that
extract poorly get a warning log, never an error. A per-page garble
heuristic (Japanese text that extracts with almost no CJK characters, or
with combining-diacritics/replacement-character noise) also warns, so the
operator notices a bad extraction at ingest time. Only a PDF that yields
no text at all (image-only scan) aborts the ingest.
"""

from pathlib import Path

import pymupdf
import structlog

from pulse_books.errors import PdfExtractionError

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)

# Pages with fewer non-space characters than this are too small to judge
# for garbling (chapter dividers, page numbers, ...).
_QUALITY_MIN_CHARS = 40
# A garbled CID extraction shows up as combining diacritics / replacement
# characters; clean text has essentially none.
_SUSPICIOUS_RATIO_LIMIT = 0.05
# Secondary signal: a "Japanese" page that extracts with almost no CJK at
# all *and* some suspicious characters is a mapping failure, not English.
_CJK_FLOOR = 0.05
_SUSPICIOUS_FLOOR = 0.01
# How many garbled page numbers to include in the warning log.
_GARBLED_PAGES_LOGGED = 10


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x3000 <= cp <= 0x30FF  # CJK punctuation, hiragana, katakana
        or 0x3400 <= cp <= 0x4DBF  # CJK extension A
        or 0x4E00 <= cp <= 0x9FFF  # CJK unified ideographs
        or 0xF900 <= cp <= 0xFAFF  # CJK compatibility ideographs
        or 0xFF00 <= cp <= 0xFFEF  # halfwidth / fullwidth forms
    )


def _is_suspicious(ch: str) -> bool:
    cp = ord(ch)
    return (
        cp == 0xFFFD  # replacement character
        or 0x0300 <= cp <= 0x036F  # combining diacritical marks
        or 0xE000 <= cp <= 0xF8FF  # private use area
    )


def looks_garbled(text: str) -> bool:
    """Heuristic: does this page's text look like a failed CID extraction?

    English-only pages (code listings, front matter) are fine: they have
    no CJK but also no suspicious characters. Short texts are never judged.
    """
    chars = [ch for ch in text if not ch.isspace()]
    total = len(chars)
    if total < _QUALITY_MIN_CHARS:
        return False
    suspicious_ratio = sum(1 for ch in chars if _is_suspicious(ch)) / total
    if suspicious_ratio > _SUSPICIOUS_RATIO_LIMIT:
        return True
    cjk_ratio = sum(1 for ch in chars if _is_cjk(ch)) / total
    return cjk_ratio < _CJK_FLOOR and suspicious_ratio > _SUSPICIOUS_FLOOR


def extract_text(pdf_path: Path) -> str:
    """Extract the full text of a PDF, pages joined by blank lines.

    The page join ("\\n\\n") doubles as a paragraph boundary for the
    chunker's PARAGRAPH strategy.
    """
    if not pdf_path.is_file():
        raise PdfExtractionError(f"PDF not found: {pdf_path}")

    try:
        document = pymupdf.open(str(pdf_path))
    except Exception as exc:
        raise PdfExtractionError(f"failed to open PDF {pdf_path}: {exc}") from exc

    try:
        if document.needs_pass:
            # Owner-password-only PDFs open without this branch; needing a
            # pass means a user (read) password. Try the empty password once
            # — some producers set an empty user password explicitly — and
            # reject the rest as DRM (C-15).
            if not document.authenticate(""):
                raise PdfExtractionError(
                    f"PDF requires a password to open, cannot ingest (C-15): {pdf_path}"
                )
        return _extract_pages(document, pdf_path)
    finally:
        document.close()


def _extract_pages(document: pymupdf.Document, pdf_path: Path) -> str:
    page_texts: list[str] = []
    empty_pages = 0
    garbled_pages: list[int] = []
    for page_number, page in enumerate(document, start=1):
        try:
            text = str(page.get_text()).strip()
        except Exception as exc:
            logger.warning("pdf: page extraction failed", page=page_number, error=str(exc))
            text = ""
        if text:
            page_texts.append(text)
            if looks_garbled(text):
                garbled_pages.append(page_number)
        else:
            empty_pages += 1

    total_pages = document.page_count
    if empty_pages:
        logger.warning(
            "pdf: some pages produced no text (image page or extraction limit)",
            empty_pages=empty_pages,
            total_pages=total_pages,
        )
    if garbled_pages:
        logger.warning(
            "pdf: some pages look garbled (CID/font mapping issue?) — "
            "their chunks will be low quality",
            garbled_pages=len(garbled_pages),
            total_pages=total_pages,
            pages=garbled_pages[:_GARBLED_PAGES_LOGGED],
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
