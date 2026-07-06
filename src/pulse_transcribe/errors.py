"""Error taxonomy for the transcribe worker.

Mirrors the backend consumer's failure classes (internal/jobs/consumer.go):
a permanent error fails the job terminally, anything else is retried until
the attempts ceiling (3). BudgetExceededError is the D-14 signal: audio
that can never fit the full nightly budget is cut off terminally (§5.3),
audio that merely does not fit *tonight's remainder* is deferred to the
next night without consuming an attempt (a deferral is not a failure).
"""


class PermanentJobError(Exception):
    """A failure retrying cannot fix (backend: jobs.Permanent).

    Examples: malformed payload, referenced article row gone.
    """


class PayloadError(PermanentJobError):
    """jobs.payload does not match the TranscribePayload contract."""


class BudgetExceededError(Exception):
    """The audio does not fit the remaining D-14 budget.

    Raised strictly before any transcription compute is spent (and before
    any state is written), which is what makes the worker's no-attempt
    deferral legal. The worker decides between deferral and terminal
    cut-off by comparing duration_seconds with the full nightly budget.
    """

    def __init__(self, duration_seconds: float, remaining_seconds: float) -> None:
        self.duration_seconds = duration_seconds
        self.remaining_seconds = remaining_seconds
        super().__init__(
            "nightly audio budget exceeded (D-14): "
            f"audio {duration_seconds:.0f}s > remaining {remaining_seconds:.0f}s"
        )


class TranscriptionError(Exception):
    """Transcription produced no usable text or the tooling failed (retryable)."""
