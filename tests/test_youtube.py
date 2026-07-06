"""Stage 2 (subtitles) / stage 3 (Whisper) fallback tests, all I/O faked."""

from pathlib import Path

import pytest

from pulse_transcribe.errors import BudgetExceededError
from pulse_transcribe.whisper import TranscriptionResult
from pulse_transcribe.youtube import (
    VideoInfo,
    _parse_json3,
    _parse_vtt_or_srt,
    extract_subtitle_text,
    transcribe_youtube,
)

URL = "https://www.youtube.com/watch?v=abc123"


class FakeTranscriber:
    def __init__(self, result: TranscriptionResult | None = None) -> None:
        self.result = result
        self.calls: list[tuple[Path, float | None]] = []

    def transcribe(
        self, audio_path: Path, max_duration_seconds: float | None = None
    ) -> TranscriptionResult:
        self.calls.append((audio_path, max_duration_seconds))
        if self.result is None:
            raise AssertionError("whisper must not be called in this scenario")
        return self.result


def track(url: str, ext: str = "vtt") -> dict[str, str]:
    return {"url": url, "ext": ext}


VTT_BODY = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello world\n"


def fake_download_factory(recorded: list[Path]):  # type: ignore[no-untyped-def]
    def download(url: str, dest_dir: Path) -> Path:
        recorded.append(dest_dir)
        audio = dest_dir / "audio.m4a"
        audio.write_bytes(b"fake-audio")
        return audio

    return download


# --- subtitle track selection ------------------------------------------------


def test_official_subtitles_preferred_over_auto_captions() -> None:
    info = VideoInfo(
        duration_seconds=100.0,
        language="en",
        subtitles={"en": [track("https://subs/official.vtt")]},
        automatic_captions={"en": [track("https://subs/auto.vtt")]},
    )
    fetched: list[str] = []

    def fetch(url: str) -> str:
        fetched.append(url)
        return VTT_BODY

    result = transcribe_youtube(URL, 7200.0, FakeTranscriber(), probe=lambda u: info, fetch=fetch)  # type: ignore[arg-type]

    assert fetched == ["https://subs/official.vtt"]
    assert result.text == "hello world"
    assert result.audio_seconds == 0.0  # subtitles cost nothing (D-14)


def test_video_language_preferred_then_ja_then_en() -> None:
    info = VideoInfo(
        duration_seconds=None,
        language="en",
        subtitles={"ja": [track("https://subs/ja.vtt")], "en": [track("https://subs/en.vtt")]},
    )
    text = extract_subtitle_text(info, fetch=lambda url: VTT_BODY if "en" in url else "")
    assert text == "hello world"  # en (the video's language) won over ja


def test_language_prefix_variants_match() -> None:
    info = VideoInfo(
        duration_seconds=None,
        language=None,
        subtitles={"en-US": [track("https://subs/en-us.vtt")]},
    )
    assert extract_subtitle_text(info, fetch=lambda url: VTT_BODY) == "hello world"


def test_json3_format_preferred_over_vtt() -> None:
    info = VideoInfo(
        duration_seconds=None,
        language=None,
        subtitles={
            "en": [track("https://subs/en.vtt", "vtt"), track("https://subs/en.json3", "json3")]
        },
    )
    fetched: list[str] = []

    def fetch(url: str) -> str:
        fetched.append(url)
        return '{"events": [{"segs": [{"utf8": "from json3"}]}]}'

    assert extract_subtitle_text(info, fetch=fetch) == "from json3"
    assert fetched == ["https://subs/en.json3"]


def test_unsupported_formats_are_skipped() -> None:
    info = VideoInfo(
        duration_seconds=None,
        language=None,
        subtitles={"en": [track("https://subs/en.ttml", "ttml")]},
    )
    assert extract_subtitle_text(info, fetch=lambda url: "irrelevant") is None


def test_broken_official_track_falls_back_to_auto_captions() -> None:
    info = VideoInfo(
        duration_seconds=None,
        language=None,
        subtitles={"en": [track("https://subs/broken.vtt")]},
        automatic_captions={"en": [track("https://subs/auto.vtt")]},
    )

    def fetch(url: str) -> str:
        if "broken" in url:
            raise OSError("HTTP 404")
        return VTT_BODY

    assert extract_subtitle_text(info, fetch=fetch) == "hello world"


def test_empty_official_track_falls_back_to_auto_captions() -> None:
    info = VideoInfo(
        duration_seconds=None,
        language=None,
        subtitles={"en": [track("https://subs/empty.vtt")]},
        automatic_captions={"en": [track("https://subs/auto.vtt")]},
    )

    def fetch(url: str) -> str:
        return "WEBVTT\n" if "empty" in url else VTT_BODY

    assert extract_subtitle_text(info, fetch=fetch) == "hello world"


# --- subtitle parsing ---------------------------------------------------------


def test_parse_json3_joins_segments_and_dedupes_lines() -> None:
    raw = (
        '{"events": ['
        '{"segs": [{"utf8": "first "}, {"utf8": "line\\n"}]},'
        '{"segs": [{"utf8": "second line\\n"}]},'
        '{"segs": [{"utf8": "second line\\n"}]},'
        "{}"
        "]}"
    )
    assert _parse_json3(raw) == "first line\nsecond line"


def test_parse_vtt_strips_cues_tags_and_rolling_duplicates() -> None:
    raw = (
        "WEBVTT\n"
        "Kind: captions\n"
        "Language: en\n"
        "\n"
        "00:00:00.000 --> 00:00:02.000 align:start\n"
        "<c.colorCCCCCC>rolling line</c>\n"
        "\n"
        "00:00:02.000 --> 00:00:04.000\n"
        "rolling line\n"
        "next &amp; final line\n"
    )
    assert _parse_vtt_or_srt(raw) == "rolling line\nnext & final line"


def test_parse_srt_skips_cue_indexes() -> None:
    raw = (
        "1\n00:00:00,000 --> 00:00:02,000\nline one\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\nline two\n"
    )
    assert _parse_vtt_or_srt(raw) == "line one\nline two"


# --- stage 3 fallback ---------------------------------------------------------


def test_no_subtitles_falls_back_to_whisper_and_cleans_up() -> None:
    info = VideoInfo(duration_seconds=600.0, language=None)
    transcriber = FakeTranscriber(TranscriptionResult("whisper text", 600.0, "en"))
    dirs: list[Path] = []

    result = transcribe_youtube(
        URL,
        7200.0,
        transcriber,  # type: ignore[arg-type]
        probe=lambda u: info,
        download=fake_download_factory(dirs),
        fetch=lambda url: pytest.fail("no subtitle URL should be fetched"),
    )

    assert result.text == "whisper text"
    assert result.audio_seconds == 600.0
    (audio_path, max_duration) = transcriber.calls[0]
    assert max_duration == 7200.0
    assert not dirs[0].exists()  # temp dir removed (§8 非永続)


def test_metadata_duration_over_budget_defers_before_download() -> None:
    info = VideoInfo(duration_seconds=8000.0, language=None)
    downloads: list[Path] = []

    with pytest.raises(BudgetExceededError):
        transcribe_youtube(
            URL,
            7200.0,
            FakeTranscriber(),  # type: ignore[arg-type]
            probe=lambda u: info,
            download=fake_download_factory(downloads),
        )
    assert downloads == []  # 事前判定: nothing was downloaded


def test_temp_dir_cleaned_up_when_whisper_fails() -> None:
    info = VideoInfo(duration_seconds=60.0, language=None)
    dirs: list[Path] = []

    class ExplodingTranscriber(FakeTranscriber):
        def transcribe(
            self, audio_path: Path, max_duration_seconds: float | None = None
        ) -> TranscriptionResult:
            raise RuntimeError("whisper crashed")

    with pytest.raises(RuntimeError):
        transcribe_youtube(
            URL,
            7200.0,
            ExplodingTranscriber(),  # type: ignore[arg-type]
            probe=lambda u: info,
            download=fake_download_factory(dirs),
        )
    assert not dirs[0].exists()
