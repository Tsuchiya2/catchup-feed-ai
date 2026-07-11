"""jobs payload contract tests (backend entity.TranscribePayload /
entity.BookIngestPayload)."""

import pytest

from pulse_transcribe.errors import PayloadError
from pulse_transcribe.models import BookIngestPayload, TranscribePayload


def test_parse_valid_dict() -> None:
    payload = TranscribePayload.parse(
        {"article_id": 42, "media_url": "https://youtu.be/x", "source_kind": "youtube"}
    )
    assert payload.article_id == 42
    assert payload.media_url == "https://youtu.be/x"
    assert payload.source_kind == "youtube"


def test_parse_valid_json_string() -> None:
    payload = TranscribePayload.parse(
        '{"article_id": 7, "media_url": " https://pod.example/e1.mp3 ", "source_kind": "podcast"}'
    )
    assert payload.article_id == 7
    assert payload.media_url == "https://pod.example/e1.mp3"  # stripped
    assert payload.source_kind == "podcast"


@pytest.mark.parametrize(
    "raw",
    [
        "not json at all",
        "[1, 2]",
        [1, 2],
        None,
        {"media_url": "https://x", "source_kind": "youtube"},  # article_id missing
        {"article_id": 0, "media_url": "https://x", "source_kind": "youtube"},
        {"article_id": -3, "media_url": "https://x", "source_kind": "youtube"},
        {"article_id": True, "media_url": "https://x", "source_kind": "youtube"},
        {"article_id": "42", "media_url": "https://x", "source_kind": "youtube"},
        {"article_id": 42, "media_url": "", "source_kind": "youtube"},
        {"article_id": 42, "media_url": "   ", "source_kind": "youtube"},
        {"article_id": 42, "source_kind": "youtube"},  # media_url missing
        {"article_id": 42, "media_url": "https://x", "source_kind": "rss"},
        {"article_id": 42, "media_url": "https://x"},  # source_kind missing
    ],
)
def test_parse_rejects_bad_payloads(raw: object) -> None:
    with pytest.raises(PayloadError):
        TranscribePayload.parse(raw)


# --- BookIngestPayload (D-25) -------------------------------------------------


def test_book_parse_valid_dict() -> None:
    payload = BookIngestPayload.parse(
        {"file_path": "/data/books/learning-go.pdf", "title": "Learning Go"}
    )
    assert payload.file_path == "/data/books/learning-go.pdf"
    assert payload.title == "Learning Go"
    assert payload.filename == "learning-go.pdf"


def test_book_parse_valid_json_string_strips_whitespace() -> None:
    payload = BookIngestPayload.parse(
        '{"file_path": " /data/books/リーダブルコード.pdf ", "title": " リーダブルコード "}'
    )
    assert payload.file_path == "/data/books/リーダブルコード.pdf"
    assert payload.title == "リーダブルコード"
    assert payload.filename == "リーダブルコード.pdf"


def test_book_filename_uses_posix_semantics() -> None:
    # The payload path is a Pi (Linux) path, whatever OS the worker is on.
    payload = BookIngestPayload.parse({"file_path": "/a/b/c.pdf", "title": "t"})
    assert payload.filename == "c.pdf"


@pytest.mark.parametrize(
    "raw",
    [
        "not json at all",
        "[1, 2]",
        [1, 2],
        None,
        {"title": "t"},  # file_path missing
        {"file_path": "", "title": "t"},
        {"file_path": "   ", "title": "t"},
        {"file_path": 42, "title": "t"},
        {"file_path": "/data/books/", "title": "t"},  # no filename
        {"file_path": "/data/books/..", "title": "t"},
        {"file_path": "/data/books/x.pdf"},  # title missing
        {"file_path": "/data/books/x.pdf", "title": ""},
        {"file_path": "/data/books/x.pdf", "title": "   "},
        {"file_path": "/data/books/x.pdf", "title": 7},
    ],
)
def test_book_parse_rejects_bad_payloads(raw: object) -> None:
    with pytest.raises(PayloadError):
        BookIngestPayload.parse(raw)
