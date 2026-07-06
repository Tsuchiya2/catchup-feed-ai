"""Podcast intake tests (download layer faked)."""

import io
from pathlib import Path
from typing import Any

import pytest

from pulse_transcribe.errors import PayloadError
from pulse_transcribe.media import download_media, transcribe_podcast
from pulse_transcribe.whisper import TranscriptionResult


class FakeTranscriber:
    def __init__(self, result: TranscriptionResult) -> None:
        self.result = result
        self.calls: list[tuple[Path, float | None]] = []

    def transcribe(
        self, audio_path: Path, max_duration_seconds: float | None = None
    ) -> TranscriptionResult:
        self.calls.append((audio_path, max_duration_seconds))
        return self.result


def test_transcribe_podcast_downloads_measures_and_cleans_up() -> None:
    transcriber = FakeTranscriber(TranscriptionResult("podcast text", 1800.0, "ja"))
    dirs: list[Path] = []

    def download(url: str, dest_dir: Path) -> Path:
        dirs.append(dest_dir)
        audio = dest_dir / "episode.mp3"
        audio.write_bytes(b"fake-mp3")
        return audio

    result = transcribe_podcast(
        "https://pod.example/e1.mp3",
        7200.0,
        transcriber,  # type: ignore[arg-type]
        download=download,
    )

    assert result.text == "podcast text"
    assert result.audio_seconds == 1800.0  # measured after download (D-14 実測)
    assert transcriber.calls[0][1] == 7200.0  # remaining budget forwarded
    assert not dirs[0].exists()  # temp dir removed (§8 非永続)


def test_temp_dir_cleaned_up_on_download_failure() -> None:
    dirs: list[Path] = []

    def download(url: str, dest_dir: Path) -> Path:
        dirs.append(dest_dir)
        raise OSError("HTTP 500")

    with pytest.raises(OSError):
        transcribe_podcast(
            "https://pod.example/e1.mp3",
            7200.0,
            FakeTranscriber(TranscriptionResult("", 0.0, None)),  # type: ignore[arg-type]
            download=download,
        )
    assert not dirs[0].exists()


@pytest.mark.parametrize("url", ["ftp://pod.example/e1.mp3", "file:///etc/passwd", "not-a-url"])
def test_download_media_rejects_non_http_urls(url: str, tmp_path: Path) -> None:
    with pytest.raises(PayloadError):
        download_media(url, tmp_path)


def test_download_media_streams_to_named_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> io.BytesIO:
        assert request.get_header("User-agent", "").startswith("pulse-transcribe")
        return io.BytesIO(b"audio-bytes")

    monkeypatch.setattr("pulse_transcribe.media.urllib.request.urlopen", fake_urlopen)

    dest = download_media("https://pod.example/shows/e42.mp3?token=x", tmp_path)

    assert dest == tmp_path / "e42.mp3"  # name from the URL path, query dropped
    assert dest.read_bytes() == b"audio-bytes"
