"""Shared test helpers: a tiny in-test PDF builder (pymupdf).

The book RAG tests need real PDF bytes without shipping a fixture file.
pymupdf builds them directly (ASCII text via the built-in Helvetica font —
fine for structural tests; Japanese behavior is covered at the chunker
level and via the looks_garbled heuristic with plain strings).

Encryption knobs mirror the two real-world cases the extractor must
distinguish: owner-password-only PDFs (freely readable, must ingest) and
user-password PDFs (a real read password, rejected per C-15).
"""

from pathlib import Path
from typing import Protocol

import pymupdf
import pytest


class MakePdf(Protocol):
    def __call__(
        self,
        page_texts: list[str],
        *,
        user_password: str | None = None,
        owner_password: str | None = None,
    ) -> Path: ...


def write_pdf(
    path: Path,
    page_texts: list[str],
    *,
    user_password: str | None = None,
    owner_password: str | None = None,
) -> Path:
    """Write a PDF with one page per text ("" makes a blank page).

    Passing only owner_password produces an "encrypted but freely readable"
    PDF (empty user password) like commercial DRM-free books.
    """
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page(width=612, height=792)
        if text:
            page.insert_text((72, 72), text, fontsize=12)
    if user_password is not None or owner_password is not None:
        document.save(
            str(path),
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=user_password or "",
            owner_pw=owner_password or "",
        )
    else:
        document.save(str(path))
    document.close()
    return path


@pytest.fixture
def make_pdf(tmp_path: Path) -> MakePdf:
    """Factory fixture: make_pdf(["page one text", ...]) -> Path."""
    counter = 0

    def _make(
        page_texts: list[str],
        *,
        user_password: str | None = None,
        owner_password: str | None = None,
    ) -> Path:
        nonlocal counter
        counter += 1
        return write_pdf(
            tmp_path / f"test-{counter}.pdf",
            page_texts,
            user_password=user_password,
            owner_password=owner_password,
        )

    return _make
