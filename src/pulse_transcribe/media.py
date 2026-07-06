"""Podcast intake (§5.2): download the RSS enclosure, transcribe with Whisper.

Podcast enclosures carry no reliable duration metadata in the job payload,
so the D-14 budget check happens after download: faster-whisper reports the
decoded audio duration before any transcription compute is spent (see
WhisperTranscriber.transcribe), which is the cheapest possible 実測.
"""

import shutil
import urllib.request
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import structlog

from pulse_transcribe.models import Transcript, require_http_url
from pulse_transcribe.whisper import WhisperTranscriber

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)

_DOWNLOAD_TIMEOUT_SECONDS = 600.0
_USER_AGENT = "pulse-transcribe/0.1"


def download_media(url: str, dest_dir: Path) -> Path:
    """Stream a media URL (podcast enclosure) into dest_dir.

    Redirects are followed (enclosure URLs commonly bounce through CDNs).
    """
    require_http_url(url)

    name = Path(urlsplit(url).path).name or "media"
    dest = dest_dir / name
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as resp:  # noqa: S310
        with dest.open("wb") as out:
            shutil.copyfileobj(resp, out)
    return dest


def transcribe_podcast(
    media_url: str,
    remaining_budget_seconds: float,
    transcriber: WhisperTranscriber,
    *,
    download: Callable[[str, Path], Path] = download_media,
) -> Transcript:
    """Download one enclosure and transcribe it.

    The audio file lives only inside the temporary directory (§8: 非永続)
    and is removed on success and failure alike.
    """
    with TemporaryDirectory(prefix="pulse-transcribe-") as tmp:
        audio_path = download(media_url, Path(tmp))
        result = transcriber.transcribe(audio_path, max_duration_seconds=remaining_budget_seconds)
        return Transcript(text=result.text, audio_seconds=result.duration_seconds)
