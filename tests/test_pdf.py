"""Tests for PDF text extraction (pulse_books.pdf)."""

from pathlib import Path

import pytest
from conftest import MakePdf

from pulse_books.errors import PdfExtractionError
from pulse_books.pdf import extract_text, looks_garbled


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


def test_owner_password_only_pdf_ingests(make_pdf: MakePdf) -> None:
    """C-15 refinement: encrypted-but-freely-readable PDFs are legitimate.

    Commercial DRM-free books often carry an owner password only (empty
    user password); readers open them without asking anything.
    """
    pdf = make_pdf(["Owner-locked but readable content."], owner_password="owner-secret")

    text = extract_text(pdf)

    assert "Owner-locked but readable content." in text


def test_user_password_pdf_is_rejected(make_pdf: MakePdf) -> None:
    """A PDF that needs a real password to open stays out of scope (C-15)."""
    pdf = make_pdf(
        ["You should never see this."],
        user_password="read-secret",
        owner_password="owner-secret",
    )

    with pytest.raises(PdfExtractionError, match="C-15"):
        extract_text(pdf)


class TestLooksGarbled:
    """The per-page CID-garble heuristic behind the ingest quality warning."""

    def test_clean_japanese_page(self) -> None:
        text = "リーダブルコードは、読みやすいコードを書くための実践的な技法を解説する本です。" * 3
        assert not looks_garbled(text)

    def test_clean_english_page(self) -> None:
        # English/code pages have no CJK but also nothing suspicious.
        text = "func main() { ch := make(chan int); go worker(ch) } // idiomatic Go " * 3
        assert not looks_garbled(text)

    def test_cid_garbled_page(self) -> None:
        # What pypdf produced on embedded-font pages: Latin base letters
        # buried under combining diacritical marks (U+0300–U+036F).
        garbled = "i͡aͭ͘uͧe͜" * 20
        assert looks_garbled(garbled)

    def test_replacement_characters_page(self) -> None:
        text = ("本文��" * 30) + "残りは読める文章です。"
        assert looks_garbled(text)

    def test_short_text_is_never_judged(self) -> None:
        assert not looks_garbled("���")
        assert not looks_garbled("")
