"""Poll-loop logic tests with a faked store, clock and handler.

Covers the semantics ported from the backend consumer (retry policy,
attempts ceiling, failure containment) plus the worker-specific guards:
the D-14 nightly audio budget, the --deadline cutoff and the
budget-exempt book_ingest drain (D-25).
"""

from datetime import datetime, timedelta

import pytest

from pulse_transcribe.db import Job
from pulse_transcribe.errors import BudgetExceededError, PermanentJobError
from pulse_transcribe.models import BookIngestPayload, TranscribePayload, Transcript
from pulse_transcribe.worker import (
    JOB_KIND_BOOK_INGEST,
    JOB_KIND_TRANSCRIBE,
    BookHandler,
    TranscribeWorker,
    aware_now,
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
    """In-memory JobStoreLike: claims pop in insertion order, per kind."""

    def __init__(
        self, jobs: list[Job] | None = None, missing_articles: set[int] | None = None
    ) -> None:
        self.pending: list[Job] = list(jobs or [])
        self.claims: list[Job] = []
        self.claim_kinds: list[tuple[str, ...]] = []
        self.done: list[int] = []
        self.failed: list[tuple[int, str, datetime | None]] = []
        self.deferred: list[int] = []
        self.contents: dict[int, str] = {}
        self.requeue_calls: list[tuple[str, ...]] = []
        self.op_order: list[str] = []
        self.missing_articles = missing_articles or set()

    def requeue_running(self, *kinds: str) -> int:
        self.requeue_calls.append(kinds)
        return 0

    def claim_next(self, *kinds: str) -> Job | None:
        self.claim_kinds.append(kinds)
        for index, job in enumerate(self.pending):
            if job.kind in kinds:
                self.pending.pop(index)
                self.claims.append(job)
                return job
        return None

    def mark_done(self, job_id: int) -> None:
        self.op_order.append(f"done:{job_id}")
        self.done.append(job_id)

    def mark_failed(self, job_id: int, last_error: str, retry_at: datetime | None) -> None:
        self.op_order.append(f"failed:{job_id}")
        self.failed.append((job_id, last_error, retry_at))

    def defer(self, job_id: int) -> None:
        self.op_order.append(f"defer:{job_id}")
        self.deferred.append(job_id)

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


def make_book_job(
    job_id: int = 1,
    attempts: int = 1,
    file_path: str = "/data/books/learning-go.pdf",
    title: str = "Learning Go",
) -> Job:
    """A claimed book_ingest job as the store returns it (D-25)."""
    return Job(
        id=job_id,
        kind=JOB_KIND_BOOK_INGEST,
        payload={"file_path": file_path, "title": title},
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
    book_handler: BookHandler | None = None,
) -> TranscribeWorker:
    return TranscribeWorker(
        store=store,
        handler=handler,  # type: ignore[arg-type]
        book_handler=book_handler,
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


def test_budget_deferral_returns_job_to_queue_and_ends_the_night() -> None:
    """D-14: a job that does not fit tonight's remainder (but fits the full

    budget) is deferred — not failed: attempts are rolled back via
    store.defer and the worker stops claiming for the night.
    """
    clock = FakeClock()
    store = FakeStore(
        [
            make_job(job_id=1, article_id=11),
            make_job(job_id=2, article_id=12),
            make_job(job_id=3, article_id=13),
        ]
    )

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        if payload.article_id == 11:
            return Transcript("text", 2000.0)
        # 6000s fits the full 7200s budget but not tonight's 5200s remainder.
        raise BudgetExceededError(6000.0, remaining)

    consumed = make_worker(store, handler, clock, budget_seconds=7200.0).run(
        deadline_in(clock, 86000)
    )

    assert store.deferred == [2]  # returned to the queue, attempts rolled back
    assert store.failed == []  # a deferral is not a failure
    assert [j.id for j in store.claims] == [1, 2]  # night ends: job 3 not claimed
    assert len(store.pending) == 1
    assert store.done == [1]
    assert consumed == 2000.0  # the deferred job consumed no budget


def test_budget_deferral_ignores_the_attempts_ceiling() -> None:
    """A deferral consumes no attempt, so the ceiling is irrelevant to it."""
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1, attempts=3)])

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        raise BudgetExceededError(6000.0, remaining)

    make_worker(store, handler, clock, budget_seconds=7200.0).run(deadline_in(clock, 60))

    assert store.deferred == [1]
    assert store.failed == []


def test_audio_exceeding_the_full_budget_fails_terminally() -> None:
    """D-14 / §5.3 足切り: audio longer than the whole nightly budget can

    never fit, so it is failed permanently instead of deferred — and the
    night continues for the jobs behind it.
    """
    clock = FakeClock()
    store = FakeStore([make_job(job_id=1, article_id=11), make_job(job_id=2, article_id=12)])

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        if payload.article_id == 11:
            raise BudgetExceededError(9000.0, remaining)  # 9000s > full 7200s
        return Transcript("text", 100.0)

    consumed = make_worker(store, handler, clock, budget_seconds=7200.0).run(
        deadline_in(clock, 3600)
    )

    job_id, last_error, retry_at = store.failed[0]
    assert job_id == 1
    assert retry_at is None  # terminal
    assert "never fit" in last_error and "D-14" in last_error
    assert store.deferred == []
    assert store.done == [2]  # not a deferral: the loop kept claiming
    assert consumed == 100.0


def test_defer_error_still_ends_the_night() -> None:
    class BrokenDeferStore(FakeStore):
        def defer(self, job_id: int) -> None:
            raise RuntimeError("connection lost")

    clock = FakeClock()
    store = BrokenDeferStore([make_job(job_id=1), make_job(job_id=2, article_id=12)])

    def handler(payload: TranscribePayload, remaining: float) -> Transcript:
        raise BudgetExceededError(6000.0, remaining)

    make_worker(store, handler, clock, budget_seconds=7200.0).run(deadline_in(clock, 3600))

    # The row stays running (swept at next start); no second claim tonight.
    assert [j.id for j in store.claims] == [1]
    assert store.failed == []


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


# --- book_ingest (D-25) ------------------------------------------------------


def test_book_jobs_drain_before_transcribe_and_skip_the_budget() -> None:
    """D-25: book jobs run first and are exempt from the D-14 budget —

    a zero-remaining transcribe budget must not starve them, and their
    processing must not consume audio seconds.
    """
    clock = FakeClock()
    store = FakeStore(
        [
            make_job(job_id=1, article_id=11),
            make_book_job(job_id=2),
            make_book_job(job_id=3, file_path="/data/books/other.pdf", title="Other"),
        ]
    )
    ingested: list[BookIngestPayload] = []

    consumed = make_worker(
        store,
        lambda p, r: Transcript("text", 100.0),
        clock,
        book_handler=ingested.append,
    ).run(deadline_in(clock, 3600))

    # Books first (even though the transcribe job was enqueued earlier).
    assert [j.id for j in store.claims] == [2, 3, 1]
    assert store.done == [2, 3, 1]
    assert [p.title for p in ingested] == ["Learning Go", "Other"]
    assert consumed == 100.0  # only the transcribe job counted (D-14 untouched)


def test_book_jobs_run_even_with_zero_transcribe_budget() -> None:
    clock = FakeClock()
    store = FakeStore([make_book_job(job_id=1)])

    make_worker(
        store,
        lambda p, r: Transcript("x", 0.0),
        clock,
        budget_seconds=0.0,
        book_handler=lambda payload: None,
    ).run(deadline_in(clock, 3600))

    assert store.done == [1]


def test_without_book_handler_book_jobs_are_never_claimed() -> None:
    clock = FakeClock()
    store = FakeStore([make_book_job(job_id=1)])

    make_worker(store, lambda p, r: Transcript("x", 0.0), clock).run(deadline_in(clock, 5))

    assert store.claims == []
    assert len(store.pending) == 1  # left pending (degraded mode)
    assert store.requeue_calls == [(JOB_KIND_TRANSCRIBE,)]
    assert all(kinds == (JOB_KIND_TRANSCRIBE,) for kinds in store.claim_kinds)


def test_startup_requeue_includes_book_kind_when_enabled() -> None:
    clock = FakeClock()
    store = FakeStore()

    make_worker(
        store, lambda p, r: Transcript("x", 0.0), clock, book_handler=lambda payload: None
    ).run(deadline_in(clock, 5))

    assert store.requeue_calls == [(JOB_KIND_TRANSCRIBE, JOB_KIND_BOOK_INGEST)]


def test_book_failure_uses_the_shared_retry_policy() -> None:
    clock = FakeClock()
    store = FakeStore([make_book_job(job_id=1, attempts=1)])

    def handler(payload: BookIngestPayload) -> None:
        raise RuntimeError("ollama down")

    make_worker(store, lambda p, r: Transcript("x", 0.0), clock, book_handler=handler).run(
        deadline_in(clock, 60)
    )

    job_id, last_error, retry_at = store.failed[0]
    assert job_id == 1
    assert last_error == "ollama down"
    assert retry_at == START + timedelta(minutes=1)  # linear-minutes backoff
    assert store.done == []


def test_book_failure_at_attempts_ceiling_is_terminal() -> None:
    clock = FakeClock()
    store = FakeStore([make_book_job(job_id=1, attempts=3)])

    def handler(payload: BookIngestPayload) -> None:
        raise RuntimeError("still broken")

    make_worker(store, lambda p, r: Transcript("x", 0.0), clock, book_handler=handler).run(
        deadline_in(clock, 60)
    )
    assert store.failed[0][2] is None


def test_book_permanent_error_is_terminal() -> None:
    clock = FakeClock()
    store = FakeStore([make_book_job(job_id=1, attempts=1)])

    def handler(payload: BookIngestPayload) -> None:
        raise PermanentJobError("PDF not found on the Pi (HTTP 404)")

    make_worker(store, lambda p, r: Transcript("x", 0.0), clock, book_handler=handler).run(
        deadline_in(clock, 60)
    )
    assert store.failed == [(1, "PDF not found on the Pi (HTTP 404)", None)]


def test_book_malformed_payload_fails_terminally_without_calling_handler() -> None:
    clock = FakeClock()
    bad = Job(
        id=1,
        kind=JOB_KIND_BOOK_INGEST,
        payload={"file_path": "/data/books/x.pdf"},  # title missing
        status="running",
        attempts=1,
        last_error=None,
        run_after=START,
        created_at=START,
    )
    store = FakeStore([bad])
    calls: list[BookIngestPayload] = []

    make_worker(store, lambda p, r: Transcript("x", 0.0), clock, book_handler=calls.append).run(
        deadline_in(clock, 60)
    )

    assert calls == []
    assert store.failed[0][2] is None  # permanent


def test_one_failing_book_job_does_not_kill_the_drain() -> None:
    clock = FakeClock()
    store = FakeStore(
        [make_book_job(job_id=1), make_book_job(job_id=2, file_path="/data/books/b.pdf")]
    )

    def handler(payload: BookIngestPayload) -> None:
        if payload.filename == "learning-go.pdf":
            raise RuntimeError("boom")

    make_worker(store, lambda p, r: Transcript("x", 0.0), clock, book_handler=handler).run(
        deadline_in(clock, 60)
    )

    assert store.failed[0][0] == 1
    assert store.done == [2]


def test_deadline_stops_book_claims_but_lets_ingest_finish() -> None:
    clock = FakeClock()
    deadline = deadline_in(clock, 60)
    store = FakeStore([make_book_job(job_id=1), make_book_job(job_id=2)])

    def slow_handler(payload: BookIngestPayload) -> None:
        clock.advance(3600)  # the in-flight ingest runs past the deadline

    make_worker(store, lambda p, r: Transcript("x", 0.0), clock, book_handler=slow_handler).run(
        deadline
    )

    assert [j.id for j in store.claims] == [1]  # job 2 waits for the next night
    assert store.done == [1]


def test_book_claim_error_ends_the_drain_but_not_the_night() -> None:
    class BrokenBookClaimStore(FakeStore):
        def claim_next(self, *kinds: str) -> Job | None:
            if JOB_KIND_BOOK_INGEST in kinds:
                raise RuntimeError("db hiccup")
            return super().claim_next(*kinds)

    clock = FakeClock()
    store = BrokenBookClaimStore([make_job(job_id=1)])

    make_worker(
        store, lambda p, r: Transcript("text", 10.0), clock, book_handler=lambda payload: None
    ).run(deadline_in(clock, 60))

    assert store.done == [1]  # the transcribe loop still ran


def test_book_mark_done_failure_is_logged_not_fatal() -> None:
    class FlakyStore(FakeStore):
        def mark_done(self, job_id: int) -> None:
            raise RuntimeError("connection lost")

    clock = FakeClock()
    store = FlakyStore([make_book_job(job_id=1), make_book_job(job_id=2)])

    make_worker(
        store, lambda p, r: Transcript("x", 0.0), clock, book_handler=lambda payload: None
    ).run(deadline_in(clock, 60))

    # Both processed; neither done nor failed (row stays running, swept
    # back to pending at the next start — re-ingest is idempotent).
    assert [j.id for j in store.claims] == [1, 2]
    assert store.failed == []


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


# --- timezone-awareness (B-1) ------------------------------------------------


def test_production_clock_is_timezone_aware() -> None:
    """jobs.run_after is timestamptz; a naive datetime would be reinterpreted

    in the server session time zone (UTC on the Pi), shifting retries by
    the local UTC offset.
    """
    stamp = aware_now()
    assert stamp.tzinfo is not None
    assert stamp.utcoffset() is not None


def test_worker_default_clock_is_the_aware_one() -> None:
    worker = TranscribeWorker(store=FakeStore(), handler=lambda p, r: Transcript("x", 0.0))
    assert worker.now().tzinfo is not None


def test_next_deadline_preserves_timezone() -> None:
    now = aware_now().replace(hour=3, minute=0, second=0, microsecond=0)
    deadline = next_deadline(parse_deadline("04:15"), now)
    assert deadline.tzinfo == now.tzinfo
    assert deadline - now == timedelta(hours=1, minutes=15)
