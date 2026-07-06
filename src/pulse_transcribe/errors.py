"""Error taxonomy for the transcribe worker.

Mirrors the backend consumer's failure classes (internal/jobs/consumer.go):
a permanent error fails the job terminally, anything else is retried until
the attempts ceiling (3). BudgetExceededError is the D-14 carry-over: the
job is rescheduled for the next night instead of the next minute.
"""


class PermanentJobError(Exception):
    """A failure retrying cannot fix (backend: jobs.Permanent).

    Examples: malformed payload, referenced article row gone.
    """


class PayloadError(PermanentJobError):
    """jobs.payload does not match the TranscribePayload contract."""


class BudgetExceededError(Exception):
    """The audio does not fit tonight's D-14 budget; carry over to the next night."""

    def __init__(self, duration_seconds: float, remaining_seconds: float) -> None:
        self.duration_seconds = duration_seconds
        self.remaining_seconds = remaining_seconds
        super().__init__(
            "deferred: nightly audio budget exceeded (D-14): "
            f"audio {duration_seconds:.0f}s > remaining {remaining_seconds:.0f}s"
        )


class TranscriptionError(Exception):
    """Transcription produced no usable text or the tooling failed (retryable)."""
