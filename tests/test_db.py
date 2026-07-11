"""JobStore unit tests with a faked psycopg connection (no database).

The full SQL semantics live in tests/test_db_integration.py (gated by
TEST_DATABASE_URL); here we pin behavior that a fake cursor can prove,
like the defer() status guard.
"""

from types import TracebackType
from typing import Any

import pytest

from pulse_transcribe.db import JobStore, JobStoreError


class FakeCursor:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount
        self.executed: list[tuple[str, Any]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def execute(self, query: str, params: Any = None) -> None:
        self.executed.append((query, params))


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> FakeCursor:
        return self._cursor


def test_defer_only_touches_a_running_row() -> None:
    """The guard: a stray defer (double-started worker, wrong id) must not

    silently decrement attempts on a pending/done/failed row — the UPDATE
    matches status='running' only and a miss surfaces as JobStoreError.
    """
    cursor = FakeCursor(rowcount=0)
    store = JobStore(FakeConnection(cursor))  # type: ignore[arg-type]

    with pytest.raises(JobStoreError):
        store.defer(7)

    query, params = cursor.executed[0]
    assert "status = 'running'" in query
    assert "attempts = attempts - 1" in query
    assert params == (7,)


def test_defer_succeeds_when_the_running_row_matches() -> None:
    cursor = FakeCursor(rowcount=1)
    JobStore(FakeConnection(cursor)).defer(7)  # type: ignore[arg-type]
    assert len(cursor.executed) == 1
