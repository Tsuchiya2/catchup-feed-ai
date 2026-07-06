"""Tests for PDF text extraction (pulse_books.pdf)."""

from collections.abc import Callable
from pathlib import Path

import pytest

from pulse_books.errors import PdfExtractionError
from pulse_books.pdf import extract_text

# The make_pdf factory fixture from conftest.py.
MakePdf = Callable[[list[str]], Path]


def test_extracts_text_from_all_pages(make_pdf: MakePdf) -> None:
    pdf = make_pdf(["First page about goroutines.", "Second page about channels."])

    text = extract_text(pdf)

    assert "First page about goroutines." in text
    assert "Second page about channels." in text
    # Pages are joined with a paragraph boundary for the chunker.
    assert text.index("goroutines") < text.index("channels")
    assert "\n\n" in text


def test_blank_pages_are_tolerated_with_remaining_text(make_pdf: MakePdf) -> None:
    """Per-page extraction failure is a warning, not an error (design §6)."""
    pdf = make_pdf(["", "Only this page has text.", ""])

    text = extract_text(pdf)

    assert text == "Only this page has text."


def test_pdf_with_no_text_at_all_raises(make_pdf: MakePdf) -> None:
    pdf = make_pdf(["", ""])

    with pytest.raises(PdfExtractionError, match="no text could be extracted"):
        extract_text(pdf)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PdfExtractionError, match="not found"):
        extract_text(tmp_path / "nope.pdf")


def test_non_pdf_file_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.pdf"
    bogus.write_bytes(b"this is not a pdf")

    with pytest.raises(PdfExtractionError):
        extract_text(bogus)
