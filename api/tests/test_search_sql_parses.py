"""Every SQL shape the archive search builds, run against a real ClickHouse.

A statement ClickHouse rejects is invisible to the rest of the suite. The
builders are ordinary string formatting, so a condition naming a column that
does not exist assembles perfectly and fails only when a server parses it —
which is how `d.has_decision` on a query reading `FROM decisions AS d` reached
production and returned 503 to every search.

So these tests take the SQL the application would actually send, and send it.
`LIMIT 0` means no rows are read and no data is needed; identifier resolution,
type checking and function arity all still happen. An empty schema is enough.

Skipped when there is no server to talk to, which is every laptop without one.
CI's `migrations` job has applied every migration to a fresh container by the
time this runs, so there it is not skipped.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib import error, request

import pytest

from app.services import search

CLICKHOUSE_URL = os.environ.get("CLICKHOUSE_URL", "")
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")

needs_clickhouse = pytest.mark.skipif(
    not CLICKHOUSE_URL,
    reason="no CLICKHOUSE_URL; the migrations job supplies one",
)

# Every branch `run()` can take, and the filters that reach the WHERE clause.
# Each entry is a plan the archivist agent can legitimately produce.
PLANS: list[tuple[str, dict[str, Any]]] = [
    ("bare", {}),
    ("scene", {"scene": 12}),
    ("scene and setup", {"scene": 12, "setup": 3}),
    ("a single take", {"scene": 12, "setup": 3, "take": 4}),
    ("outcome", {"outcome": "rejected"}),
    ("decided_by", {"decided_by": "human"}),
    ("outcome and decided_by", {"outcome": "selected", "decided_by": "agent"}),
    ("a named finding", {"finding": "focus.lost"}),
    ("a finding within a scene", {"finding": "stability.shake", "scene": 4}),
    ("a finding with an outcome", {"finding": "focus.lost", "outcome": "rejected"}),
    ("free text", {"text": "she enters"}),
    ("text with an outcome", {"text": "boom in frame", "outcome": "rejected"}),
    ("semantic intent", {"semantic": "a wide shot at dusk"}),
    ("oldest first", {"scene": 1, "newest_first": False}),
    ("an explicit limit", {"limit": 5}),
]


def _execute(sql: str) -> None:
    """Send one statement. Raises with the server's own message on rejection."""
    req = request.Request(
        f"{CLICKHOUSE_URL}/?wait_end_of_query=1",
        data=sql.encode("utf-8"),
        method="POST",
    )
    if CLICKHOUSE_PASSWORD:
        from base64 import b64encode

        token = b64encode(f"{CLICKHOUSE_USER}:{CLICKHOUSE_PASSWORD}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")

    try:
        request.urlopen(req, timeout=30).read()
    except error.HTTPError as exc:
        raise AssertionError(exc.read().decode("utf-8", "replace")[:800]) from None


def _limit_zero(sql: str) -> str:
    """Read nothing, parse everything.

    The trailing `LIMIT {n}` is replaced rather than appended — ClickHouse takes
    the first LIMIT in a statement, so appending would leave the real one in
    force and read rows that an empty schema does not have.
    """
    return re.sub(r"LIMIT\s+\d+\s*$", "LIMIT 0", sql.strip())


async def _sql_for(plan: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> str:
    """The statement `run()` would send, captured instead of sent.

    Patching `_execute` rather than reimplementing the builders is the whole
    point: a query shape that exists only inside `run()` is still covered, and
    a new branch added later is covered without anybody remembering to add it
    here.
    """
    captured: dict[str, str] = {}

    async def capture(sql: str, params: dict[str, Any], project_id: int):
        captured["sql"] = search._interpolated(sql, params)
        return [], 0

    monkeypatch.setattr(search, "_execute", capture)

    embedding = [0.0] * 768 if plan.get("semantic") else None
    await search.run(6, plan, embedding)
    return captured["sql"]


class TestEverySearchShapeParses:
    @needs_clickhouse
    @pytest.mark.parametrize("name,plan", PLANS, ids=[p[0] for p in PLANS])
    @pytest.mark.asyncio
    async def test_clickhouse_accepts_it(
        self, name: str, plan: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _execute(_limit_zero(await _sql_for(plan, monkeypatch)))

    @needs_clickhouse
    @pytest.mark.asyncio
    async def test_the_widened_query_parses_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`widen` runs when nothing matched, which is the moment a broken
        query is least likely to be noticed and most likely to be blamed on an
        empty archive."""
        captured: dict[str, str] = {}

        async def capture(sql: str, params: dict[str, Any], project_id: int):
            captured["sql"] = search._interpolated(sql, params)
            return [], 0

        monkeypatch.setattr(search, "_execute", capture)
        await search.widen(6, {"scene": 12, "outcome": "rejected"})
        _execute(_limit_zero(captured["sql"]))


class TestTheHarnessItself:
    """A test that cannot fail proves nothing, so this proves it can."""

    @needs_clickhouse
    def test_a_bad_identifier_is_rejected(self) -> None:
        with pytest.raises(AssertionError, match=r"(?i)identifier|unknown|missing"):
            _execute("SELECT no_such_column FROM decisions LIMIT 0")

    @needs_clickhouse
    def test_a_good_statement_is_accepted(self) -> None:
        _execute("SELECT clip_id FROM decisions LIMIT 0")
