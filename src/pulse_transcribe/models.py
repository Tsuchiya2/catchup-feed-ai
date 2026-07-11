"""Shared value types: the jobs payload contracts and the transcript result."""

import json
import posixpath
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
class BookIngestPayload:
    """jobs.payload for kind='book_ingest' (D-25).

    Contract owner: backend entity.BookIngestPayload
    (catchup-feed-backend/internal/domain/entity/job.go). Exactly these
    keys; renames are a cross-repo breaking change.

    file_path is the canonical absolute path of the PDF **as seen by the
    Pi server** (BOOKS_DIR + sanitized filename) — the identity key of the
    book (books.file_path). The Mac worker never reads this path from its
    own filesystem: it downloads the PDF from the tailnet-only endpoint
    GET {BOOKS_PRIVATE_BASE_URL}/private/books/{filename}.
    """

    file_path: str
    title: str

    @property
    def filename(self) -> str:
        """The basename of the Pi path — the /private/books/{filename} segment.

        posixpath, not os.path: the payload path is a Pi (Linux) path
        regardless of what OS the worker runs on.
        """
        return posixpath.basename(self.file_path)

    @classmethod
    def parse(cls, raw: object) -> BookIngestPayload:
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

        file_path = raw.get("file_path")
        if not isinstance(file_path, str) or not file_path.strip():
            raise PayloadError(f"payload.file_path must be a non-empty string, got {file_path!r}")
        file_path = file_path.strip()
        basename = posixpath.basename(file_path)
        if not basename or basename in (".", ".."):
            raise PayloadError(f"payload.file_path has no usable filename: {file_path!r}")

        title = raw.get("title")
        if not isinstance(title, str) or not title.strip():
            raise PayloadError(f"payload.title must be a non-empty string, got {title!r}")

        return cls(file_path=file_path, title=title.strip())


@dataclass(frozen=True, slots=True)
class Transcript:
    """The outcome of one transcribe job.

    audio_seconds is what counts against the D-14 nightly budget: the
    duration of audio actually run through Whisper. A subtitle-based
    transcript costs 0.0 (no audio was processed).
    """

    text: str
    audio_seconds: float
