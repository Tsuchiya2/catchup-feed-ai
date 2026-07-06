"""WhisperTranscriber tests with a faked faster-whisper model."""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pulse_transcribe.errors import BudgetExceededError, TranscriptionError
from pulse_transcribe.whisper import WhisperTranscriber


class FakeModel:
    def __init__(self, texts: list[str], duration: float, language: str | None = "en") -> None:
        self.texts = texts
        self.duration = duration
        self.language = language
        self.decoded = False
        self.options: dict[str, Any] = {}

    def transcribe(self, audio: str, **options: Any) -> tuple[Iterator[Any], Any]:
        self.options = options

        def segments() -> Iterator[Any]:
            self.decoded = True  # consuming the generator = spending compute
            for text in self.texts:
                yield SimpleNamespace(text=text)

        info = SimpleNamespace(duration=self.duration, language=self.language)
        return segments(), info


def make_transcriber(model: FakeModel) -> tuple[WhisperTranscriber, list[int]]:
    factory_calls: list[int] = []

    def factory() -> FakeModel:
        factory_calls.append(1)
        return model

    return WhisperTranscriber(model_factory=factory), factory_calls


def test_transcribe_joins_stripped_segments() -> None:
    model = FakeModel([" hello ", "", "  world"], duration=42.5, language="en")
    transcriber, _ = make_transcriber(model)

    result = transcriber.transcribe(Path("/tmp/a.mp3"))

    assert result.text == "hello\nworld"
    assert result.duration_seconds == 42.5
    assert result.language == "en"
    # Long-form stability settings (faster-whisper standard features).
    assert model.options["vad_filter"] is True
    assert model.options["condition_on_previous_text"] is False


def test_budget_check_happens_before_any_decoding() -> None:
    model = FakeModel(["never decoded"], duration=9000.0)
    transcriber, _ = make_transcriber(model)

    with pytest.raises(BudgetExceededError) as exc_info:
        transcriber.transcribe(Path("/tmp/a.mp3"), max_duration_seconds=7200.0)

    assert model.decoded is False  # no compute was spent (D-14 事前判定)
    assert exc_info.value.duration_seconds == 9000.0


def test_duration_exactly_at_budget_is_transcribed() -> None:
    model = FakeModel(["ok"], duration=7200.0)
    transcriber, _ = make_transcriber(model)
    result = transcriber.transcribe(Path("/tmp/a.mp3"), max_duration_seconds=7200.0)
    assert result.text == "ok"


def test_model_is_loaded_once(tmp_path: Path) -> None:
    model = FakeModel(["x"], duration=1.0)
    transcriber, factory_calls = make_transcriber(model)
    transcriber.transcribe(tmp_path / "a.mp3")
    transcriber.transcribe(tmp_path / "b.mp3")
    assert len(factory_calls) == 1


def test_model_errors_become_transcription_errors() -> None:
    class BrokenModel:
        def transcribe(self, audio: str, **options: Any) -> tuple[Any, Any]:
            raise RuntimeError("cannot decode audio")

    transcriber = WhisperTranscriber(model_factory=lambda: BrokenModel())
    with pytest.raises(TranscriptionError):
        transcriber.transcribe(Path("/tmp/a.mp3"))
