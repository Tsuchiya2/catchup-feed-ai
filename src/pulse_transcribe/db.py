"""jobs table access — a Python port of the backend's JobRepo.

The SQL semantics are copied verbatim from
catchup-feed-backend/internal/infra/adapter/persistence/postgres/job_repo.go
(ClaimNext / MarkDone / MarkFailed / RequeueRunning). The backend is the
contract owner; do not extend the state machine here.

The only adaptation: the kind list is bound as `kind = ANY(%s)` (the
psycopg idiom) instead of Go's generated `kind IN ($1, ...)` placeholders —
identical semantics. RequeueRunning is additionally scoped to this worker's
kinds; see requeue_running below. defer() implements the D-14 carry-over
sanctioned by the backend contract (job_repository.go: an *unstarted*
claimed job may be returned to pending with its attempts increment rolled
back).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

# Mirrors the backend's jobs.status values (entity/job.go).
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

# Mirrors the backend's RequeueRunning last_error text (job_repo.go).
_REQUEUE_LAST_ERROR = "requeued: claimed by a worker that did not finish (stale running sweep)"


class JobStoreError(Exception):
    """A jobs-table operation did not behave as expected (e.g. no rows affected)."""


@dataclass(frozen=True, slots=True)
class Job:
    """One row of the jobs table (backend entity.Job).

    attempts is the post-claim value: ClaimNext increments it, so attempts=1
    means "this is the first execution" — the retry ceiling compares against
    this value, exactly like the backend consumer.
    """

    id: int
    kind: str
    payload: object  # jsonb; psycopg loads it as a Python object
    status: str
    attempts: int
    last_error: str | None
    run_after: datetime
    created_at: datetime


class JobStore:
    """DB-backed queue client. The connection must be in autocommit mode

    (each statement commits on its own, like Go's database/sql), so the
    FOR UPDATE SKIP LOCKED row lock in claim_next lives exactly as long as
    the single UPDATE statement — the same behavior as the backend.
    """

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def claim_next(self, *kinds: str) -> Job | None:
        """Atomically claim the oldest runnable pending job of the given kinds.

        Marks the row running and increments attempts; FOR UPDATE SKIP LOCKED
        keeps concurrent consumers from double-claiming (backend ClaimNext).
        Returns None when nothing is runnable.
        """
        query = """
UPDATE jobs SET
       status   = 'running',
       attempts = attempts + 1
WHERE id = (
    SELECT id FROM jobs
    WHERE status = 'pending' AND run_after <= now() AND kind = ANY(%s)
    ORDER BY run_after ASC, id ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING id, kind, payload, status, attempts, last_error, run_after, created_at"""
        with self._conn.cursor() as cur:
            cur.execute(query, (list(kinds),))
            row = cur.fetchone()
        if row is None:
            return None
        return Job(
            id=row[0],
            kind=row[1],
            payload=row[2],
            status=row[3],
            attempts=row[4],
            last_error=row[5],
            run_after=row[6],
            created_at=row[7],
        )

    def mark_done(self, job_id: int) -> None:
        """Finish a claimed job successfully (backend MarkDone)."""
        with self._conn.cursor() as cur:
            cur.execute("UPDATE jobs SET status = 'done' WHERE id = %s", (job_id,))
            if cur.rowcount == 0:
                raise JobStoreError("mark_done: no rows affected")

    def mark_failed(self, job_id: int, last_error: str, retry_at: datetime | None) -> None:
        """Record the error (backend MarkFailed).

        With retry_at set the job goes back to pending with
        run_after = retry_at (attempts stay incremented from the claim);
        with retry_at None the job is failed terminally.
        """
        with self._conn.cursor() as cur:
            if retry_at is not None:
                cur.execute(
                    "UPDATE jobs SET status = 'pending', last_error = %s, run_after = %s"
                    " WHERE id = %s",
                    (last_error, retry_at, job_id),
                )
            else:
                cur.execute(
                    "UPDATE jobs SET status = 'failed', last_error = %s WHERE id = %s",
                    (last_error, job_id),
                )
            if cur.rowcount == 0:
                raise JobStoreError("mark_failed: no rows affected")

    def defer(self, job_id: int) -> None:
        """Return an *unstarted* claimed job to the queue without consuming

        an attempt (D-14 carry-over): status back to pending, the claim's
        attempts increment rolled back. run_after is left unchanged — the
        worker stops claiming for the night after its first deferral, so
        the job is simply first in line the next night.

        Only legal while processing has not started (nothing written, no
        transcription compute spent); once a job has started, failures must
        go through mark_failed. Backend contract note: repository.JobRepository
        (job_repository.go) permits the attempts rollback for untouched jobs.

        The status guard keeps a stray defer (e.g. two workers started by
        hand) from silently decrementing attempts on a row someone else
        already released or finished.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status = 'pending', attempts = attempts - 1"
                " WHERE id = %s AND status = 'running'",
                (job_id,),
            )
            if cur.rowcount == 0:
                raise JobStoreError("defer: no running row for the job")

    def requeue_running(self, *kinds: str) -> int:
        """Flip stale running jobs of our kinds back to pending (backend RequeueRunning).

        The backend sweeps the whole table because its consumer is the only
        consumer of the whole queue; that assumption holds here only
        per-kind (the Pi worker consumes other kinds concurrently), so the
        sweep is scoped to the kinds this worker owns. This worker is the
        sole consumer of kind='transcribe', so at startup a running
        transcribe job can only be the orphan of a crashed previous run.
        """
        query = """
UPDATE jobs SET
       status     = 'pending',
       last_error = %s
WHERE status = 'running' AND kind = ANY(%s)"""
        with self._conn.cursor() as cur:
            cur.execute(query, (_REQUEUE_LAST_ERROR, list(kinds)))
            return cur.rowcount

    def update_article_content(self, article_id: int, content: str) -> bool:
        """Store the transcript as the article's full text (§4: articles.content).

        Returns False when the article row no longer exists (a permanent
        failure for the caller).
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE articles SET content = %s WHERE id = %s",
                (content, article_id),
            )
            return cur.rowcount > 0
