"""Shared value types: the jobs payload contract and the transcript result."""

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from pulse_transcribe.errors import PayloadError

SOURCE_KIND_YOUTUBE = "youtube"
SOURCE_KIND_PODCAST = "podcast"
_SOURCE_KINDS = frozenset({SOURCE_KIND_YOUTUBE, SOURCE_KIND_PODCAST})


def require_http_url(url: str) -> str:
    """Reject non-http(s) media URLs before they reach any downloader.

    A permanent failure: a file:// or ftp:// payload will never become
    fetchable by retrying.
    """
    scheme = urlsplit(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise PayloadError(f"media_url must be http(s), got scheme {scheme!r}")
    return url


@dataclass(frozen=True, slots=True)
class TranscribePayload:
    """jobs.payload for kind='transcribe'.

    Contract owner: backend entity.TranscribePayload
    (catchup-feed-backend/internal/domain/entity/job.go). Exactly these
    keys; renames are a cross-repo breaking change.
    """

    article_id: int
    media_url: str
    source_kind: str  # 'youtube' | 'podcast'

    @classmethod
    def parse(cls, raw: object) -> TranscribePayload:
        """Parse a jobs.payload value (dict from psycopg jsonb, or a JSON string).

        Raises PayloadError (permanent: retrying cannot fix a bad payload).
        """
        if isinstance(raw, str | bytes):
            try:
                raw = json.loads(raw)
            except ValueError as exc:
                raise PayloadError(f"payload is not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise PayloadError(f"payload must be a JSON object, got {type(raw).__name__}")

        article_id = raw.get("article_id")
        if isinstance(article_id, bool) or not isinstance(article_id, int) or article_id <= 0:
            raise PayloadError(f"payload.article_id must be a positive integer, got {article_id!r}")

        media_url = raw.get("media_url")
        if not isinstance(media_url, str) or not media_url.strip():
            raise PayloadError(f"payload.media_url must be a non-empty string, got {media_url!r}")

        source_kind = raw.get("source_kind")
        if source_kind not in _SOURCE_KINDS:
            raise PayloadError(
                f"payload.source_kind must be one of {sorted(_SOURCE_KINDS)}, got {source_kind!r}"
            )

        return cls(article_id=article_id, media_url=media_url.strip(), source_kind=source_kind)


@dataclass(frozen=True, slots=True)
class Transcript:
    """The outcome of one transcribe job.

    audio_seconds is what counts against the D-14 nightly budget: the
    duration of audio actually run through Whisper. A subtitle-based
    transcript costs 0.0 (no audio was processed).
    """

    text: str
    audio_seconds: float
