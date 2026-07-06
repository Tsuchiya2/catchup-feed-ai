"""jobs poll loop — the Mac-side counterpart of the backend's jobs.Consumer.

Status transitions, the attempts ceiling (3) and the SKIP LOCKED claim are
a faithful port of catchup-feed-backend/internal/jobs (consumer.go) — the
backend implementation is the contract owner. On top of that the loop adds
only what §5 / D-14 require of the nightly batch:

- D-14: stop claiming once the transcribed audio total reaches the nightly
  budget (2h); audio that provably would not fit is deferred to the next
  night (a retryable failure with a next-night run_after, still subject to
  the attempts ceiling — §5.3 長尺の足切り).
- --deadline (default 04:15): stop claiming past the deadline so radio's
  04:30 slot is never invaded; an in-flight job is allowed to finish.
- Degradation (§5.3): a job failure is contained by MarkFailed; the loop
  itself never dies because of one job.
"""

import argparse
import logging
import time as time_module
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Protocol

import structlog

from pulse_transcribe.config import Settings
from pulse_transcribe.db import Job
from pulse_transcribe.errors import BudgetExceededError, PermanentJobError, TranscriptionError
from pulse_transcribe.models import SOURCE_KIND_YOUTUBE, TranscribePayload, Transcript

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)

# The only kind this worker claims (backend entity.JobKindTranscribe).
JOB_KIND_TRANSCRIBE = "transcribe"

# Backend jobs.DefaultMaxAttempts — the §7 retry ceiling.
MAX_ATTEMPTS = 3

# Backend default retry backoff: linear minutes (consumer.go retryDelay).
_RETRY_DELAY_PER_ATTEMPT = timedelta(minutes=1)

# D-14 carry-over: a budget-deferred job must not become claimable again
# tonight (the linear-minutes backoff would burn all attempts within one
# run). 20 hours from the 03:00–04:15 window always lands before the next
# night's window.
DEFER_DELAY = timedelta(hours=20)

# Stop claiming at this local time so radio (04:30) is never invaded.
DEFAULT_DEADLINE = "04:15"


class JobStoreLike(Protocol):
    """The slice of db.JobStore the loop needs (also fulfilled by test fakes)."""

    def claim_next(self, *kinds: str) -> Job | None: ...
    def mark_done(self, job_id: int) -> None: ...
    def mark_failed(self, job_id: int, last_error: str, retry_at: datetime | None) -> None: ...
    def requeue_running(self, *kinds: str) -> int: ...
    def update_article_content(self, article_id: int, content: str) -> bool: ...


# handler(payload, remaining_budget_seconds) -> Transcript.
Handler = Callable[[TranscribePayload, float], Transcript]


@dataclass(slots=True)
class TranscribeWorker:
    store: JobStoreLike
    handler: Handler
    budget_seconds: float = 7200.0  # D-14
    poll_interval_seconds: float = 10.0
    max_attempts: int = MAX_ATTEMPTS
    defer_delay: timedelta = DEFER_DELAY
    now: Callable[[], datetime] = field(default=datetime.now)
    sleep: Callable[[float], None] = field(default=time_module.sleep)

    def run(self, deadline: datetime) -> float:
        """Consume transcribe jobs until the deadline or the D-14 budget.

        Returns the total audio seconds transcribed (for logs and tests).
        """
        log = logger.bind(deadline=deadline.isoformat())

        # Startup sweep, scoped to our own kind: this worker is the sole
        # consumer of kind='transcribe', so a running row at startup can
        # only be the orphan of a crashed previous run. Never sweep other
        # kinds — the Pi worker owns those.
        try:
            requeued = self.store.requeue_running(JOB_KIND_TRANSCRIBE)
            if requeued > 0:
                log.warning("jobs: requeued stale running jobs from a previous run", count=requeued)
        except Exception as exc:
            # Non-fatal, same as the backend: the jobs stay claimable later.
            log.error("jobs: stale running sweep failed", error=str(exc))

        log.info(
            "jobs: transcribe worker started",
            kind=JOB_KIND_TRANSCRIBE,
            budget_seconds=self.budget_seconds,
            poll_interval=self.poll_interval_seconds,
            max_attempts=self.max_attempts,
        )

        consumed = 0.0
        while True:
            if self.now() >= deadline:
                log.info("jobs: deadline reached, stopping", audio_seconds=round(consumed, 1))
                break
            if consumed >= self.budget_seconds:
                log.info(
                    "jobs: nightly audio budget exhausted (D-14), stopping",
                    audio_seconds=round(consumed, 1),
                )
                break

            try:
                job = self.store.claim_next(JOB_KIND_TRANSCRIBE)
            except Exception as exc:
                log.error("jobs: claim failed", error=str(exc))
                job = None

            if job is not None:
                consumed += self._process(job, self.budget_seconds - consumed)
                continue  # drain the backlog without sleeping

            remaining = (deadline - self.now()).total_seconds()
            if remaining > 0:
                self.sleep(min(self.poll_interval_seconds, remaining))

        return consumed

    def _process(self, job: Job, remaining_budget_seconds: float) -> float:
        """Execute one claimed job; returns the audio seconds it consumed.

        Mirrors the backend consumer's process(): success marks done, any
        failure goes through the retry policy. Audio seconds are counted
        whenever Whisper actually ran, even if a later step failed — the
        compute was spent either way.
        """
        log = logger.bind(job_id=job.id, kind=job.kind, attempts=job.attempts)
        log.info("jobs: job started")

        try:
            payload = TranscribePayload.parse(job.payload)
        except PermanentJobError as exc:
            self._record_failure(job, exc, log)
            return 0.0

        try:
            transcript = self.handler(payload, remaining_budget_seconds)
        except Exception as exc:
            # BudgetExceededError defers to the next night; anything else
            # follows the linear-minutes retry policy. Either way the loop
            # survives (§5.3).
            self._record_failure(job, exc, log)
            return 0.0

        if not transcript.text.strip():
            self._record_failure(job, TranscriptionError("transcription produced no text"), log)
            return transcript.audio_seconds

        try:
            updated = self.store.update_article_content(payload.article_id, transcript.text)
        except Exception as exc:
            self._record_failure(job, exc, log)
            return transcript.audio_seconds
        if not updated:
            self._record_failure(
                job, PermanentJobError(f"article {payload.article_id} not found"), log
            )
            return transcript.audio_seconds

        try:
            self.store.mark_done(job.id)
        except Exception as exc:
            # Same as the backend: log and move on. The row stays running
            # and is swept back to pending at the next start; re-running
            # the job just overwrites articles.content (idempotent).
            log.error("jobs: mark done failed", error=str(exc))
            return transcript.audio_seconds

        log.info("jobs: job done", audio_seconds=round(transcript.audio_seconds, 1))
        return transcript.audio_seconds

    def _record_failure(
        self, job: Job, exc: Exception, log: structlog.typing.FilteringBoundLogger
    ) -> None:
        """Backend consumer's recordFailure: permanent errors and exhausted

        attempts fail terminally, everything else is rescheduled — with the
        linear-minutes backoff, or the next-night delay for D-14 deferrals.
        """
        retry_at: datetime | None = None
        if not isinstance(exc, PermanentJobError) and job.attempts < self.max_attempts:
            if isinstance(exc, BudgetExceededError):
                delay = self.defer_delay
            else:
                delay = job.attempts * _RETRY_DELAY_PER_ATTEMPT
            retry_at = self.now() + delay

        try:
            self.store.mark_failed(job.id, str(exc), retry_at)
        except Exception as mark_exc:
            log.error("jobs: mark failed failed", error=str(mark_exc), job_error=str(exc))
            return

        if retry_at is not None:
            log.warning(
                "jobs: job failed, retry scheduled",
                retry_at=retry_at.isoformat(),
                error=str(exc),
            )
        else:
            log.error("jobs: job failed terminally", error=str(exc))


def parse_deadline(value: str) -> time:
    """Parse an HH:MM CLI value into a time of day."""
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"deadline must be HH:MM, got {value!r}") from exc


def next_deadline(deadline: time, now: datetime) -> datetime:
    """The next occurrence of the given time of day strictly after now.

    Started at 03:00 with the default 04:15, that is the same morning; a
    run started after the deadline time rolls over to the next day.
    """
    candidate = now.replace(
        hour=deadline.hour, minute=deadline.minute, second=0, microsecond=0
    )
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def default_handler(settings: Settings) -> Handler:
    """The production handler: dispatch on source_kind (§5.1 / §5.2)."""
    from pulse_transcribe.media import transcribe_podcast
    from pulse_transcribe.whisper import WhisperTranscriber
    from pulse_transcribe.youtube import transcribe_youtube

    transcriber = WhisperTranscriber(
        model_name=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )

    def handle(payload: TranscribePayload, remaining_budget_seconds: float) -> Transcript:
        if payload.source_kind == SOURCE_KIND_YOUTUBE:
            return transcribe_youtube(payload.media_url, remaining_budget_seconds, transcriber)
        return transcribe_podcast(payload.media_url, remaining_budget_seconds, transcriber)

    return handle


def configure_logging(level: str) -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-transcribe",
        description="pulse Phase 2 transcribe worker (jobs poll, Mac nightly batch)",
    )
    parser.add_argument(
        "--deadline",
        type=parse_deadline,
        default=parse_deadline(DEFAULT_DEADLINE),
        metavar="HH:MM",
        help=f"stop claiming new jobs at this local time (default {DEFAULT_DEADLINE}, "
        "so the radio batch at 04:30 is never invaded)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    import psycopg

    from pulse_transcribe.db import JobStore

    args = _parse_args(argv)
    # Required fields (DATABASE_URL) come from the environment / .env;
    # pydantic-settings validates them at runtime, which mypy cannot see.
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level)

    deadline = next_deadline(args.deadline, datetime.now())

    # autocommit: each statement commits on its own (like Go's database/sql),
    # which is what the SKIP LOCKED claim semantics assume.
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        worker = TranscribeWorker(
            store=JobStore(conn),
            handler=default_handler(settings),
            budget_seconds=settings.nightly_budget_seconds,
            poll_interval_seconds=settings.poll_interval_seconds,
        )
        worker.run(deadline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
