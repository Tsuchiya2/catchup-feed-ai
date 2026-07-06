"""Shared test helpers: a tiny in-test PDF builder (pypdf only).

The book RAG tests need real PDF bytes without shipping a fixture file.
pypdf's writer plus a hand-built content stream is enough for ASCII text
(the built-in Helvetica font cannot encode Japanese — fine for structural
tests; Japanese behavior is covered at the chunker level with plain
strings).
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

MakePdf = Callable[[list[str]], Path]


def write_pdf(path: Path, page_texts: list[str]) -> Path:
    """Write a PDF with one page per text ("" makes a blank page)."""
    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        if not text:
            continue
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = stream
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {
                        NameObject("/F1"): DictionaryObject(
                            {
                                NameObject("/Type"): NameObject("/Font"),
                                NameObject("/Subtype"): NameObject("/Type1"),
                                NameObject("/BaseFont"): NameObject("/Helvetica"),
                            }
                        )
                    }
                )
            }
        )
    with path.open("wb") as fh:
        writer.write(fh)
    return path


@pytest.fixture
def make_pdf(tmp_path: Path) -> MakePdf:
    """Factory fixture: make_pdf(["page one text", ...]) -> Path."""
    counter = 0

    def _make(page_texts: list[str]) -> Path:
        nonlocal counter
        counter += 1
        return write_pdf(tmp_path / f"test-{counter}.pdf", page_texts)

    return _make
