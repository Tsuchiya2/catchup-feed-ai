"""YouTube stages 2 and 3 of the C-14 fallback chain (§5.1).

Stage 2: fetch subtitles via yt-dlp metadata — official tracks first, then
auto-generated captions. When a usable track exists, Whisper is skipped
entirely (0 seconds against the D-14 budget).

Stage 3: no usable subtitles — download the audio only (yt-dlp) into a
temporary directory and transcribe with faster-whisper. The video duration
from metadata is checked against the remaining nightly budget *before*
downloading (D-14 事前判定).

Stage 1 (Gemini URL input) lives in the Go backend and is out of scope here.
"""

import html
import json
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

import structlog

from pulse_transcribe.errors import BudgetExceededError, TranscriptionError
from pulse_transcribe.models import Transcript
from pulse_transcribe.whisper import WhisperTranscriber

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)

_FETCH_TIMEOUT_SECONDS = 60.0
# Subtitle formats we can turn into plain text, in preference order.
_SUPPORTED_SUB_EXTS = ("json3", "vtt", "srt")


@dataclass(frozen=True, slots=True)
class VideoInfo:
    """The slice of yt-dlp's extract_info output this module needs."""

    duration_seconds: float | None
    language: str | None
    # lang -> list of {"url": ..., "ext": ...} track variants
    subtitles: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    automatic_captions: dict[str, list[dict[str, str]]] = field(default_factory=dict)


def probe_video(url: str) -> VideoInfo:
    """Fetch video metadata (duration, subtitle tracks) without downloading."""
    from yt_dlp import YoutubeDL

    opts = {"skip_download": True, "quiet": True, "no_warnings": True, "noplaylist": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict):
        raise TranscriptionError(f"yt-dlp returned no metadata for {url}")
    duration = info.get("duration")
    return VideoInfo(
        duration_seconds=float(duration) if duration else None,
        language=info.get("language"),
        subtitles=info.get("subtitles") or {},
        automatic_captions=info.get("automatic_captions") or {},
    )


def download_audio(url: str, dest_dir: Path) -> Path:
    """Download the audio-only stream into dest_dir and return the file path."""
    from yt_dlp import YoutubeDL

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / "audio.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    if isinstance(info, dict):
        for download in info.get("requested_downloads") or []:
            filepath = download.get("filepath")
            if filepath:
                return Path(filepath)
    files = sorted(dest_dir.glob("audio.*"))
    if not files:
        raise TranscriptionError(f"yt-dlp produced no audio file for {url}")
    return files[0]


def _fetch_url_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=_FETCH_TIMEOUT_SECONDS) as resp:  # noqa: S310
        data: bytes = resp.read()
    return data.decode("utf-8", errors="replace")


def _preferred_languages(video_language: str | None) -> list[str]:
    """The video's own language first, then ja / en (日英混在ソース想定)."""
    order = []
    for lang in (video_language, "ja", "en"):
        if lang and lang not in order:
            order.append(lang)
    return order


def _pick_track(
    tracks: dict[str, list[dict[str, str]]], preferred: list[str]
) -> tuple[str, dict[str, str]] | None:
    """Pick (lang, variant): preferred languages first (exact or prefixed

    like en-US / en-orig), then any language for determinism; within a
    language the first supported format wins (json3 > vtt > srt).
    """
    candidates = [
        lang
        for pref in preferred
        for lang in sorted(tracks)
        if lang == pref or lang.startswith(pref + "-")
    ]
    candidates += [lang for lang in sorted(tracks) if lang not in candidates]
    for lang in candidates:
        variants = {v.get("ext", ""): v for v in tracks.get(lang, []) if v.get("url")}
        for ext in _SUPPORTED_SUB_EXTS:
            if ext in variants:
                return lang, variants[ext]
    return None


def _parse_json3(raw: str) -> str:
    data = json.loads(raw)
    parts: list[str] = []
    for event in data.get("events") or []:
        for seg in event.get("segs") or []:
            parts.append(seg.get("utf8", ""))
    return _normalize_lines(("".join(parts)).splitlines())


_TIMING_RE = re.compile(r"-->")
_TAG_RE = re.compile(r"<[^>]+>")


def _parse_vtt_or_srt(raw: str) -> str:
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or _TIMING_RE.search(stripped):
            continue
        if stripped == "WEBVTT" or stripped.startswith(("NOTE", "STYLE", "Kind:", "Language:")):
            continue
        if stripped.isdigit():  # srt cue index
            continue
        lines.append(html.unescape(_TAG_RE.sub("", stripped)))
    return _normalize_lines(lines)


def _normalize_lines(lines: list[str]) -> str:
    """Strip, drop empties, and dedupe consecutive repeats (rolling captions)."""
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and (not out or out[-1] != stripped):
            out.append(stripped)
    return "\n".join(out)


def _parse_subtitle(raw: str, ext: str) -> str:
    if ext == "json3":
        return _parse_json3(raw)
    return _parse_vtt_or_srt(raw)


def extract_subtitle_text(
    info: VideoInfo, fetch: Callable[[str], str] = _fetch_url_text
) -> str | None:
    """Stage 2: official subtitles first, auto captions second.

    Returns None when no usable track exists; per-track fetch/parse errors
    fall through to the next candidate (and ultimately to stage 3) instead
    of failing the job.
    """
    for source, tracks in (("official", info.subtitles), ("auto", info.automatic_captions)):
        picked = _pick_track(tracks, _preferred_languages(info.language))
        if picked is None:
            continue
        lang, variant = picked
        try:
            text = _parse_subtitle(fetch(variant["url"]), variant.get("ext", ""))
        except Exception as exc:
            logger.warning(
                "youtube: subtitle track unusable, trying next",
                source=source,
                lang=lang,
                error=str(exc),
            )
            continue
        if text.strip():
            logger.info("youtube: transcript from subtitles", source=source, lang=lang)
            return text
    return None


def transcribe_youtube(
    url: str,
    remaining_budget_seconds: float,
    transcriber: WhisperTranscriber,
    *,
    probe: Callable[[str], VideoInfo] = probe_video,
    download: Callable[[str, Path], Path] = download_audio,
    fetch: Callable[[str], str] = _fetch_url_text,
) -> Transcript:
    """Run stages 2 and 3 for one YouTube video."""
    info = probe(url)

    text = extract_subtitle_text(info, fetch)
    if text is not None:
        return Transcript(text=text, audio_seconds=0.0)

    # Stage 3 — pre-check the metadata duration against the D-14 budget
    # before downloading anything (事前判定).
    if info.duration_seconds is not None and info.duration_seconds > remaining_budget_seconds:
        raise BudgetExceededError(info.duration_seconds, remaining_budget_seconds)

    # Audio lives only inside this temporary directory (§8: 非永続) and is
    # removed on success and failure alike.
    with TemporaryDirectory(prefix="pulse-transcribe-") as tmp:
        audio_path = download(url, Path(tmp))
        result = transcriber.transcribe(audio_path, max_duration_seconds=remaining_budget_seconds)
        return Transcript(text=result.text, audio_seconds=result.duration_seconds)
