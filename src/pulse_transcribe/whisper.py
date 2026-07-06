"""faster-whisper wrapper (D-11: large-v3-turbo, language auto-detect).

The model is loaded lazily so that subtitle-only nights never pay the load
cost, and downloaded automatically by faster-whisper on first use (free,
from Hugging Face). Long-form stability uses only standard faster-whisper
features: VAD filtering and condition_on_previous_text=False (avoids
repetition loops on long audio).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import structlog

from pulse_transcribe.errors import BudgetExceededError, TranscriptionError

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)


class _WhisperModelLike(Protocol):
    def transcribe(self, audio: str, **options: Any) -> tuple[Any, Any]: ...


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    duration_seconds: float
    language: str | None


class WhisperTranscriber:
    """Lazy-loading faster-whisper front end."""

    def __init__(
        self,
        model_name: str = "large-v3-turbo",
        device: str = "auto",
        compute_type: str = "auto",
        model_factory: Callable[[], _WhisperModelLike] | None = None,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._model_factory = model_factory
        self._model: _WhisperModelLike | None = None

    def _load(self) -> _WhisperModelLike:
        if self._model is None:
            if self._model_factory is not None:
                self._model = self._model_factory()
            else:
                # Imported lazily: pulling in CTranslate2 is slow and only
                # needed when subtitles were not available.
                from faster_whisper import WhisperModel

                logger.info(
                    "whisper: loading model",
                    model=self._model_name,
                    device=self._device,
                    compute_type=self._compute_type,
                )
                self._model = WhisperModel(
                    self._model_name, device=self._device, compute_type=self._compute_type
                )
        return self._model

    def transcribe(
        self, audio_path: Path, max_duration_seconds: float | None = None
    ) -> TranscriptionResult:
        """Transcribe an audio file, language auto-detected.

        faster-whisper's transcribe() is lazy: it returns the audio metadata
        immediately and only does the heavy decoding while the segments
        generator is consumed. That lets us enforce the D-14 budget from the
        decoded audio duration *before* spending any transcription compute:
        if the audio is longer than max_duration_seconds, BudgetExceededError
        is raised and no segment is decoded.
        """
        model = self._load()
        try:
            segments, info = model.transcribe(
                str(audio_path),
                vad_filter=True,
                condition_on_previous_text=False,
            )
        except Exception as exc:
            raise TranscriptionError(f"whisper transcription failed: {exc}") from exc

        duration = float(info.duration)
        if max_duration_seconds is not None and duration > max_duration_seconds:
            raise BudgetExceededError(duration, max_duration_seconds)

        try:
            text = "\n".join(
                stripped for segment in segments if (stripped := segment.text.strip())
            )
        except Exception as exc:
            raise TranscriptionError(f"whisper transcription failed: {exc}") from exc

        return TranscriptionResult(
            text=text,
            duration_seconds=duration,
            language=getattr(info, "language", None),
        )
