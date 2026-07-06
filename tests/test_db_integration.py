"""Real-PostgreSQL integration tests for JobStore, gated by TEST_DATABASE_URL

(same convention as the backend's *_RealPostgres tests: unset = skip).

The jobs DDL is copied from the backend migration
(catchup-feed-backend/internal/infra/db/migrate.go §4) — the backend owns
the schema. Tables are created inside a throwaway schema so pointing
TEST_DATABASE_URL at a development database is safe.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from pulse_transcribe.db import JobStore, JobStoreError

DSN = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DSN, reason="TEST_DATABASE_URL not set; skipping real-postgres tests"
)

SCHEMA = "pulse_transcribe_it"

# Copied from backend migrate.go (§4: jobs). Keep in sync with the backend.
JOBS_DDL = """
CREATE TABLE jobs (
    id            bigserial PRIMARY KEY,
    kind          text NOT NULL,
    payload       jsonb NOT NULL DEFAULT '{}',
    status        text NOT NULL DEFAULT 'pending',
    attempts      int NOT NULL DEFAULT 0,
    last_error    text,
    run_after     timestamptz NOT NULL DEFAULT now(),
    created_at    timestamptz NOT NULL DEFAULT now()
)"""

# Backend migrate.go articles minus the sources FK (irrelevant to the
# content-update semantics under test).
ARTICLES_DDL = """
CREATE TABLE articles (
    id            bigserial PRIMARY KEY,
    source_id     bigint NOT NULL,
    url           text NOT NULL UNIQUE,
    title         text NOT NULL,
    content       text,
    published_at  timestamptz,
    crawled_at    timestamptz NOT NULL DEFAULT now()
)"""


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(DSN, autocommit=True) as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        connection.execute(f"CREATE SCHEMA {SCHEMA}")
        connection.execute(f"SET search_path TO {SCHEMA}")
        connection.execute(JOBS_DDL)
        connection.execute(ARTICLES_DDL)
        try:
            yield connection
        finally:
            connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")


@pytest.fixture
def store(conn: psycopg.Connection) -> JobStore:
    return JobStore(conn)


def enqueue(
    conn: psycopg.Connection,
    kind: str = "transcribe",
    payload: str = '{"article_id": 1, "media_url": "https://x", "source_kind": "podcast"}',
    status: str = "pending",
    run_after_offset_seconds: float = 0.0,
) -> int:
    row = conn.execute(
        "INSERT INTO jobs (kind, payload, status, run_after)"
        " VALUES (%s, %s::jsonb, %s, now() + make_interval(secs => %s)) RETURNING id",
        (kind, payload, status, run_after_offset_seconds),
    ).fetchone()
    assert row is not None
    return int(row[0])


def fetch_job(conn: psycopg.Connection, job_id: int) -> tuple:
    row = conn.execute(
        "SELECT status, attempts, last_error, run_after FROM jobs WHERE id = %s", (job_id,)
    ).fetchone()
    assert row is not None
    return row


def test_claim_marks_running_and_increments_attempts(
    conn: psycopg.Connection, store: JobStore
) -> None:
    job_id = enqueue(conn, run_after_offset_seconds=-5)

    job = store.claim_next("transcribe")

    assert job is not None
    assert job.id == job_id
    assert job.kind == "transcribe"
    assert job.status == "running"
    assert job.attempts == 1
    assert job.payload == {"article_id": 1, "media_url": "https://x", "source_kind": "podcast"}
    status, attempts, _, _ = fetch_job(conn, job_id)
    assert (status, attempts) == ("running", 1)


def test_claim_returns_none_when_nothing_runnable(store: JobStore) -> None:
    assert store.claim_next("transcribe") is None


def test_claim_orders_by_run_after_then_id(conn: psycopg.Connection, store: JobStore) -> None:
    later = enqueue(conn, run_after_offset_seconds=-10)
    earliest = enqueue(conn, run_after_offset_seconds=-30)
    tied_with_earliest = conn.execute(
        "INSERT INTO jobs (kind, run_after)"
        " SELECT kind, run_after FROM jobs WHERE id = %s RETURNING id",
        (earliest,),
    ).fetchone()
    assert tied_with_earliest is not None

    claimed = [store.claim_next("transcribe") for _ in range(3)]
    assert [job.id for job in claimed if job] == [earliest, int(tied_with_earliest[0]), later]


def test_claim_skips_future_run_after(conn: psycopg.Connection, store: JobStore) -> None:
    enqueue(conn, run_after_offset_seconds=3600)
    assert store.claim_next("transcribe") is None


def test_claim_only_requested_kinds(conn: psycopg.Connection, store: JobStore) -> None:
    other = enqueue(conn, kind="notify_episode", run_after_offset_seconds=-10)
    mine = enqueue(conn, kind="transcribe", run_after_offset_seconds=-5)

    job = store.claim_next("transcribe")
    assert job is not None and job.id == mine
    assert store.claim_next("transcribe") is None
    assert fetch_job(conn, other)[0] == "pending"  # left for the Pi worker


def test_claim_skips_rows_locked_by_another_consumer(
    conn: psycopg.Connection, store: JobStore
) -> None:
    first = enqueue(conn, run_after_offset_seconds=-20)
    second = enqueue(conn, run_after_offset_seconds=-10)

    with psycopg.connect(DSN) as other:  # not autocommit: holds the row lock
        other.execute(f"SET search_path TO {SCHEMA}")
        other.execute("SELECT id FROM jobs WHERE id = %s FOR UPDATE", (first,))

        job = store.claim_next("transcribe")  # must SKIP the locked row
        assert job is not None and job.id == second
        other.rollback()

    job = store.claim_next("transcribe")  # lock released: now claimable
    assert job is not None and job.id == first


def test_mark_done(conn: psycopg.Connection, store: JobStore) -> None:
    enqueue(conn, run_after_offset_seconds=-5)
    job = store.claim_next("transcribe")
    assert job is not None

    store.mark_done(job.id)
    assert fetch_job(conn, job.id)[0] == "done"


def test_mark_done_missing_row_raises(store: JobStore) -> None:
    with pytest.raises(JobStoreError):
        store.mark_done(999999)


def test_mark_failed_with_retry_goes_back_to_pending(
    conn: psycopg.Connection, store: JobStore
) -> None:
    enqueue(conn, run_after_offset_seconds=-5)
    job = store.claim_next("transcribe")
    assert job is not None

    retry_at = datetime.now(UTC) + timedelta(minutes=1)
    store.mark_failed(job.id, "download failed", retry_at)

    status, attempts, last_error, run_after = fetch_job(conn, job.id)
    assert status == "pending"
    assert attempts == 1  # attempts stay incremented from the claim
    assert last_error == "download failed"
    assert run_after == retry_at


def test_mark_failed_terminal(conn: psycopg.Connection, store: JobStore) -> None:
    enqueue(conn, run_after_offset_seconds=-5)
    job = store.claim_next("transcribe")
    assert job is not None

    store.mark_failed(job.id, "attempts exhausted", None)

    status, _, last_error, _ = fetch_job(conn, job.id)
    assert (status, last_error) == ("failed", "attempts exhausted")


def test_mark_failed_missing_row_raises(store: JobStore) -> None:
    with pytest.raises(JobStoreError):
        store.mark_failed(999999, "x", None)


def test_requeue_running_is_scoped_to_given_kinds(
    conn: psycopg.Connection, store: JobStore
) -> None:
    mine = enqueue(conn, kind="transcribe", status="running")
    others = enqueue(conn, kind="notify_episode", status="running")

    assert store.requeue_running("transcribe") == 1

    status, _, last_error, _ = fetch_job(conn, mine)
    assert status == "pending"
    assert last_error is not None and "stale running sweep" in last_error
    assert fetch_job(conn, others)[0] == "running"  # the Pi worker's job is untouched


def test_update_article_content(conn: psycopg.Connection, store: JobStore) -> None:
    row = conn.execute(
        "INSERT INTO articles (source_id, url, title, content)"
        " VALUES (1, 'https://youtu.be/x', 'a talk', NULL) RETURNING id"
    ).fetchone()
    assert row is not None
    article_id = int(row[0])

    assert store.update_article_content(article_id, "the transcript") is True
    content_row = conn.execute(
        "SELECT content FROM articles WHERE id = %s", (article_id,)
    ).fetchone()
    assert content_row is not None and content_row[0] == "the transcript"

    assert store.update_article_content(article_id + 1000, "orphan") is False
