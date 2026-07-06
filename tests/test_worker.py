"""Poll-loop logic tests with a faked store, clock and handler.

Covers the semantics ported from the backend consumer (retry policy,
attempts ceiling, failure containment) plus the worker-specific guards:
the D-14 nightly audio budget and the --deadline cutoff.
"""

from datetime import datetime, timedelta

import pytest

from pulse_transcribe.db import Job
from pulse_transcribe.errors import BudgetExceededError, PermanentJobError
from pulse_transcribe.models import TranscribePayload, Transcript
from pulse_transcribe.worker import (
    DEFER_DELAY,
    JOB_KIND_TRANSCRIBE,
    TranscribeWorker,
    next_deadline,
    parse_deadline,
)

START = datetime(2026, 7, 6, 3, 0, 0)


class FakeClock:
    def __init__(self, start: datetime = START) -> None:
        self.current = start
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


class FakeStore:
    """In-memory JobStoreLike: claims pop in insertion order."""

    def __init__(
        self, jobs: list[Job] | None = None, missing_articles: set[int] | None = None
    ) -> None:
        self.pending: list[Job] = list(jobs or [])
        self.claims: list[Job] = []
        self.done: list[int] = []
        self.failed: list[tuple[int, str, datetime | None]] = []
        self.contents: dict[int, str] = {}
        self.requeue_calls: list[tuple[str, ...]] = []
        self.op_order: list[str] = []
        self.missing_articles = missing_articles or set()

    def requeue_running(self, *kinds: str) -> int:
        self.requeue_calls.append(kinds)
        return 0

    def claim_next(self, *kinds: str) -> Job | None:
        if not self.pending:
            return None
        job = self.pending.pop(0)
        self.claims.append(job)
        return job

    def mark_done(self, job_id: int) -> None:
        self.op_order.append(f"done:{job_id}")
        self.done.append(job_id)

    def mark_failed(self, job_id: int, last_error: str, retry_at: datetime | None) -> None:
        self.op_order.append(f"failed:{job_id}")
        self.failed.append((job_id, last_error, retry_at))

    def update_article_content(self, article_id: int, content: str) -> bool:
        self.op_order.append(f"update:{article_id}")
        if article_id in self.missing_articles:
            return False
        self.contents[article_id] = content
        return True


def make_job(job_id: int = 1, attempts: int = 1, article_id: int = 10, **payload: object) -> Job:
    """A claimed job as the store returns it (attempts is post-claim)."""
    body: dict[str, object] = {
        "article_id": article_id,
        "media_url": f"https://pod.example/{job_id}.mp3",
        "source_kind": "podcast",
    }
    body.update(payload)
    return Job(
        id=job_id,
        kind=JOB_KIND_TRANSCRIBE,
        payload=body,
        status="running",
        attempts=attempts,
        last_error=None,
        run_after=START,
        created_at=START,
    )


def make_worker(
    store: FakeStore,
    handler: object,
    clock: FakeClock,
    budget_seconds: float = 7200.0,
    poll_interval_seconds: float = 10.0,
) -> TranscribeWorker:
    return TranscribeWorker(
        store=store,
        handler=handler,  # type: ignore[arg-type]
        budget_seconds=budget_seconds,
        poll_interval_seconds=poll_interval_seconds,
        now=clock.now,
        sleep=clock.sleep,
    )


def deadline_in(clock: FakeClock, seconds: float) -> datetime:
    return clock.current + timedelta(seconds=seconds)


def test_success_updates_content_before_mark_done() -> None:
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1, article_id=10)])
    worker = make_worker(store, lambda p, r: Transcript("full transcript", 123.0), clock)

    consumed = worker.run(deadline_in(clock, 3600))

    assert store.contents[10] == "full transcript"
    assert store.done == [1]
    assert store.op_order.index("update:10") < store.op_order.index("done:1")
    assert consumed == 123.0
    assert store.failed == []


def test_startup_requeue_is_scoped_to_transcribe() -> None:
    clock = FakeClock()
    store = FakeStore()
    make_worker(store, lambda p, r: Transcript("x", 0.0), clock).run(deadline_in(clock, 5))
    assert store.requeue_calls == [(JOB_KIND_TRANSCRIBE,)]


def test_idle_poll_sleeps_until_deadline() -> None:
    clock = FakeClock()
    store = FakeStore()
    worker = make_worker(store, lambda p, r: Transcript("x", 0.0), clock)

    consumed = worker.run(deadline_in(clock, 25))

    # 10s + 10s + capped 5s, then the deadline check exits the loop.
    assert clock.sleeps == [10.0, 10.0, 5.0]
    assert consumed == 0.0
    assert store.claims == []


def test_deadline_stops_new_claims_but_lets_job_finish() -> None:
    clock = FakeClock()
    deadline = deadline_in(clock, 60)
    store = FakeStore([make_job(job_id=1), make_job(job_id=2)])

    def slow_handler(payload: TranscribePayload, remaining: float) -> Transcript:
        clock.advance(3600)  # the in-flight job runs past the deadline
        return Transcript("text", 500.0)

    consumed = make_worker(store, slow_handler, clock).run(deadline)

    assert [j.id for j in store.claims] == [1]  # job 2 is left for the next night
    assert store.done == [1]  # the in-flight job was completed
    assert consumed == 500.0


def test_budget_cutoff_stops_claiming(  # D-14
) -> None:
    clock = FakeClock()
    store = FakeStore(
        [
            make_job(job_id=1, article_id=11),
            make_job(job_id=2, article_id=12),
            make_job(job_id=3, article_id=13),
        ]
    )
    durations = {11: 5000.0, 12: 3000.0, 13: 100.0}

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        return Transcript("text", durations[payload.article_id])

    consumed = make_worker(store, handler, clock, budget_seconds=7200.0).run(
        deadline_in(clock, 86000)
    )

    # 5000 + 3000 = 8000 >= 7200: job 3 must not be claimed.
    assert [j.id for j in store.claims] == [1, 2]
    assert len(store.pending) == 1
    assert consumed == 8000.0


def test_handler_sees_remaining_budget() -> None:
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1), make_job(job_id=2)])
    seen: list[float] = []

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        seen.append(remaining)
        return Transcript("text", 2000.0)

    make_worker(store, handler, clock, budget_seconds=7200.0).run(deadline_in(clock, 3600))
    assert seen == [7200.0, 5200.0]


def test_budget_deferral_reschedules_for_next_night() -> None:
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1, attempts=1), make_job(job_id=2, article_id=12)])

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        if payload.article_id == 10:
            raise BudgetExceededError(9000.0, remaining)
        return Transcript("text", 100.0)

    consumed = make_worker(store, handler, clock).run(deadline_in(clock, 3600))

    job_id, last_error, retry_at = store.failed[0]
    assert job_id == 1
    assert "D-14" in last_error
    assert retry_at == START + DEFER_DELAY  # next-night carry-over, not linear minutes
    # A deferral consumes no budget and does not stop the loop.
    assert store.done == [2]
    assert consumed == 100.0


def test_budget_deferral_at_attempts_ceiling_fails_terminally() -> None:
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1, attempts=3)])

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        raise BudgetExceededError(9000.0, remaining)

    make_worker(store, handler, clock).run(deadline_in(clock, 60))
    assert store.failed[0][2] is None  # terminal, §5.3 長尺の足切り


@pytest.mark.parametrize(("attempts", "delay_minutes"), [(1, 1), (2, 2)])
def test_retryable_failure_uses_linear_minutes_backoff(attempts: int, delay_minutes: int) -> None:
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1, attempts=attempts)])

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        raise RuntimeError("download failed")

    make_worker(store, handler, clock).run(deadline_in(clock, 60))

    _, last_error, retry_at = store.failed[0]
    assert last_error == "download failed"
    assert retry_at == START + timedelta(minutes=delay_minutes)


def test_failure_at_attempts_ceiling_is_terminal() -> None:
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1, attempts=3)])

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        raise RuntimeError("still broken")

    make_worker(store, handler, clock).run(deadline_in(clock, 60))
    assert store.failed[0][2] is None


def test_permanent_error_is_terminal_regardless_of_attempts() -> None:
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1, attempts=1)])

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        raise PermanentJobError("video is gone")

    make_worker(store, handler, clock).run(deadline_in(clock, 60))
    assert store.failed == [(1, "video is gone", None)]


def test_malformed_payload_fails_terminally_without_calling_handler() -> None:
    clock = FakeClock()
    bad = Job(
        id=1,
        kind=JOB_KIND_TRANSCRIBE,
        payload={"article_id": "nope"},
        status="running",
        attempts=1,
        last_error=None,
        run_after=START,
        created_at=START,
    )
    store = FakeStore([bad])
    calls: list[TranscribePayload] = []

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        calls.append(payload)
        return Transcript("x", 0.0)

    make_worker(store, handler, clock).run(deadline_in(clock, 60))
    assert calls == []
    assert store.failed[0][2] is None  # permanent


def test_missing_article_is_terminal_but_audio_still_counts() -> None:
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1, article_id=10)], missing_articles={10})
    worker = make_worker(store, lambda p, r: Transcript("text", 3600.0), clock)

    consumed = worker.run(deadline_in(clock, 60))

    assert store.failed[0][2] is None
    assert "article 10" in store.failed[0][1]
    assert consumed == 3600.0  # Whisper compute was spent either way (D-14)


def test_empty_transcript_is_a_retryable_failure_and_audio_counts() -> None:
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1, attempts=1)])
    worker = make_worker(store, lambda p, r: Transcript("   \n ", 1200.0), clock)

    consumed = worker.run(deadline_in(clock, 60))

    _, last_error, retry_at = store.failed[0]
    assert "no text" in last_error
    assert retry_at is not None
    assert consumed == 1200.0
    assert store.contents == {}


def test_one_failing_job_does_not_kill_the_loop() -> None:
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1, article_id=11), make_job(job_id=2, article_id=12)])

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        if payload.article_id == 11:
            raise RuntimeError("boom")
        return Transcript("ok", 10.0)

    make_worker(store, handler, clock).run(deadline_in(clock, 60))
    assert store.done == [2]
    assert store.failed[0][0] == 1


def test_mark_done_failure_is_logged_not_fatal() -> None:
    class FlakyStore(FakeStore):
        def mark_done(self, job_id: int) -> None:
            raise RuntimeError("connection lost")

    clock = FakeClock()
    store = FlakyStore([make_job(job_id=1), make_job(job_id=2, article_id=12)])

    consumed = make_worker(store, lambda p, r: Transcript("text", 5.0), clock).run(
        deadline_in(clock, 60)
    )

    # Both jobs processed; neither marked done, neither marked failed
    # (mirrors the backend: the row stays running, swept next start).
    assert [j.id for j in store.claims] == [1, 2]
    assert store.failed == []
    assert consumed == 10.0


def test_claim_error_is_contained_and_retried_after_sleep() -> None:
    class BrokenClaimStore(FakeStore):
        def __init__(self) -> None:
            super().__init__()
            self.claim_attempts = 0

        def claim_next(self, *kinds: str) -> Job | None:
            self.claim_attempts += 1
            raise RuntimeError("db down")

    clock = FakeClock()
    store = BrokenClaimStore()
    make_worker(store, lambda p, r: Transcript("x", 0.0), clock).run(deadline_in(clock, 15))

    assert store.claim_attempts == 2  # 0s and 10s marks, then deadline
    assert clock.sleeps == [10.0, 5.0]


# --- deadline helpers -------------------------------------------------------


def test_parse_deadline_valid() -> None:
    parsed = parse_deadline("04:15")
    assert (parsed.hour, parsed.minute) == (4, 15)


@pytest.mark.parametrize("value", ["4:5x", "24:00", "0415", "", "later"])
def test_parse_deadline_invalid(value: str) -> None:
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        parse_deadline(value)


def test_next_deadline_same_morning() -> None:
    now = datetime(2026, 7, 6, 3, 0, 0)
    assert next_deadline(parse_deadline("04:15"), now) == datetime(2026, 7, 6, 4, 15, 0)


def test_next_deadline_rolls_over_when_already_past() -> None:
    now = datetime(2026, 7, 6, 5, 0, 0)
    assert next_deadline(parse_deadline("04:15"), now) == datetime(2026, 7, 7, 4, 15, 0)


def test_next_deadline_exactly_at_deadline_rolls_over() -> None:
    now = datetime(2026, 7, 6, 4, 15, 0)
    assert next_deadline(parse_deadline("04:15"), now) == datetime(2026, 7, 7, 4, 15, 0)
