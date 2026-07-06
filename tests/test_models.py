"""TranscribePayload contract tests (backend entity.TranscribePayload)."""

import pytest

from pulse_transcribe.errors import PayloadError
from pulse_transcribe.models import TranscribePayload


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
