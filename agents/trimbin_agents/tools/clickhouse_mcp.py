"""The ClickHouse MCP client, read-only for real this time.

Every search an editor runs goes through the official `mcp-clickhouse` server,
which is how the ClickHouse track requires the database to be used at runtime.

This file once opened with the same claim and did not earn it. It said a
read-only database user was the primary defence and the keyword regex below was
a convenience; there was no read-only user, the connection was the admin one,
and the regex was the only thing between a model-written statement and the
production archive. A regex over SQL is a filter, not a boundary — a subquery, a
comment splicing a keyword, a function whose name contains a forbidden word are
all ordinary SQL and none of them are what the pattern was written for.

The user now exists. `trimbin_reader` holds SELECT on ten named objects and
nothing else, under a profile with `readonly = 1 CONST` — const so it cannot be
turned off mid-session, which is the difference between a setting and a
guarantee. See `clickhouse/migrations/011_readonly_user.sql`.

So the layers, in the order they actually stop something:

  1. the server refuses anything but SELECT, whatever statement arrives
  2. the grant limits which objects a SELECT can even name
  3. the scope filter is appended by us and never asked for in the prompt
  4. the regex rejects the obvious before it costs a round trip

Only the first two are boundaries. The other two are courtesies, and this file
now says which is which.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)

# Rejected before anything reaches the server — the fourth layer, and the least
# important one.
#
# Its job is a legible error and a saved round trip, not safety. The reader user
# and its grants are what actually stop a write; this catches the obvious cases
# early so the log says "DROP is not permitted" rather than surfacing a
# permissions failure three layers down.
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|ATTACH|DETACH|OPTIMIZE|SYSTEM)\b",
    re.IGNORECASE,
)

# One statement per call. A trailing semicolon is fine; a second statement is how
# a benign-looking SELECT carries something else behind it.
_MULTI_STATEMENT = re.compile(r";\s*\S")

MAX_ROWS = 200
QUERY_TIMEOUT_S = 30


class UnsafeQuery(ValueError):
    """The statement was refused before it was sent."""


class QueryFailed(RuntimeError):
    """The search did not run.

    Distinct from an empty result on purpose: "nothing matched" and "the search
    broke" are different answers, and a system that returns the same empty list
    for both teaches people to trust neither.
    """


@dataclass(frozen=True)
class QueryOutcome:
    rows: list[dict[str, Any]]
    sql: str
    elapsed_ms: int
    truncated: bool


def assert_read_only(sql: str) -> None:
    """Refuse anything that is not a single SELECT.

    Checked here so the refusal is explicit and greppable, rather than surfacing
    as an opaque permissions error from the server.
    """
    stripped = sql.strip().rstrip(";").strip()

    if not stripped:
        raise UnsafeQuery("empty statement")

    if _MULTI_STATEMENT.search(sql):
        raise UnsafeQuery("only one statement per query")

    if not stripped.upper().startswith(("SELECT", "WITH")):
        raise UnsafeQuery("only SELECT is permitted")

    if match := _FORBIDDEN.search(stripped):
        raise UnsafeQuery(f"{match.group(0).upper()} is not permitted")


def scope_clause(project_id: int | None) -> str:
    """The scope filter, written by us rather than asked for.

    A model told to remember which project it may look at will usually remember.
    A WHERE clause the model never sees always does, and the difference matters
    on the one request where a question is crafted to make it forget.
    """
    if project_id is None:
        raise UnsafeQuery("every query must be scoped to a project")
    return f"project_id = {int(project_id)}"


class ClickHouseMCP:
    """Thin wrapper over the official mcp-clickhouse server."""

    def __init__(self, session: Any = None) -> None:
        self._session = session

    async def run_query(
        self,
        sql: str,
        project_id: int | None,
        columns: list[str] | None = None,
    ) -> QueryOutcome:
        """Run a statement and return rows as dicts.

        `columns` is supplied by the caller because the caller wrote the SELECT
        and therefore knows its shape. mcp-clickhouse returns positional rows
        with no usable header, and guessing at whichever field a future version
        puts the names in is how six rows became "nothing matched" once already.
        """
        assert_read_only(sql)
        scope = scope_clause(project_id)

        if scope not in sql:
            raise UnsafeQuery("query is not scoped to the caller's project")

        limited = self._with_limit(sql)
        started = time.perf_counter()

        try:
            result = await self._session.call_tool("run_query", {"query": limited})
        except Exception as exc:
            raise QueryFailed(str(exc)) from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        rows = _rows_from(result, columns)

        log.info("query returned %d rows in %dms", len(rows), elapsed_ms)

        return QueryOutcome(
            rows=rows[:MAX_ROWS],
            sql=limited,
            elapsed_ms=elapsed_ms,
            truncated=len(rows) > MAX_ROWS,
        )

    @staticmethod
    def _with_limit(sql: str) -> str:
        """Bound the result whether or not the model remembered to.

        An unbounded query over a few hundred thousand decisions will return
        them all, and the cost lands on the person waiting for a page to render.
        """
        if re.search(r"\bLIMIT\s+\d+", sql, re.IGNORECASE):
            return sql
        return f"{sql.rstrip().rstrip(';')} LIMIT {MAX_ROWS + 1}"


def _rows_from(result: Any, columns: list[str] | None = None) -> list[dict[str, Any]]:
    """Unwrap whatever shape the MCP response arrived in.

    Tolerant on purpose — the transport is not the interesting part. But an
    unrecognised shape is logged rather than swallowed, because the first
    version returned an empty list for it and an empty list is indistinguishable
    from "nothing matched". A search that silently answers "no results" because
    a parser missed is the exact failure this system is built against.
    """
    import json

    content = getattr(result, "structuredContent", None)
    if content is None:
        content = getattr(result, "content", result)

    # A list of content blocks, each carrying text. The usual shape.
    if isinstance(content, list) and content and hasattr(content[0], "text"):
        text = content[0].text or ""

        # The server reports a database error as plain text in the same field it
        # uses for results. Parsed as "not JSON" and returned as an empty list,
        # that becomes "nothing matched" — which is how a result-size limit came
        # to look like an empty archive.
        if text.lstrip().startswith(("Error", "Traceback")) or "DB::Exception" in text:
            raise QueryFailed(text.strip()[:400])

        try:
            content = json.loads(text)
        except (ValueError, AttributeError):
            log.warning("MCP returned text that is not JSON: %r", text[:300])
            return []

    # Column names arrive beside the rows, not inside them.
    #
    # mcp-clickhouse returns positional rows — a list of lists — with the header
    # in a sibling field. The first version of this looked only for a list of
    # objects, found none, and returned empty. Six rows became "nothing matched",
    # which is the failure this whole file is careful about.
    # Names from the caller first. It wrote the SELECT, so it knows; anything
    # the server volunteers is a bonus, not the source of truth.
    if isinstance(content, dict):
        for key in ("columns", "column_names", "meta", "header"):
            if key in content and not columns:
                raw = content[key]
                columns = [c.get("name") if isinstance(c, dict) else str(c) for c in raw]
                break

        for key in ("rows", "data", "result", "records"):
            if key in content:
                content = content[key]
                break
        else:
            # A single row as an object is still a row.
            return [content] if content else []

    if not isinstance(content, list):
        log.warning("MCP returned an unexpected shape: %r", str(content)[:300])
        return []

    if content and isinstance(content[0], dict):
        return [r for r in content if isinstance(r, dict)]

    # Positional rows. Zipped back to names where we have them; without them a
    # row is unusable to the caller, so say that rather than returning indexes.
    if content and isinstance(content[0], list | tuple):
        if not columns:
            log.warning(
                "MCP returned positional rows with no column names: %r",
                str(content[0])[:200],
            )
            return []
        return [dict(zip(columns, row, strict=False)) for row in content]

    if content:
        log.warning("MCP rows were an unfamiliar type: %r", str(content[:2])[:300])
    return []


class ReaderMissing(RuntimeError):
    """No read-only user is configured, so MCP will not be started.

    Refusing is the point. Falling back to the admin credentials would give a
    model-written statement write access to the archive, and it would do so
    silently — which is how the previous version of this file came to claim a
    protection that did not exist.
    """


def server_env() -> dict[str, str]:
    """Environment for the MCP server process.

    Connects as `trimbin_reader`, never as the admin user. The write flags are
    set false explicitly rather than left to a default: a default is a decision
    somebody else made and can change, and this one is ours and visible.
    """
    if not (settings.clickhouse_reader_user and settings.clickhouse_reader_password):
        raise ReaderMissing(
            "TRIMBIN_CLICKHOUSE_READER_USER/PASSWORD are unset. MCP is not "
            "started without them — the admin connection is not a fallback."
        )

    return {
        "CLICKHOUSE_HOST": settings.clickhouse_host,
        "CLICKHOUSE_PORT": str(settings.clickhouse_port),
        "CLICKHOUSE_SECURE": "true",
        "CLICKHOUSE_USER": settings.clickhouse_reader_user,
        "CLICKHOUSE_PASSWORD": settings.clickhouse_reader_password,
        "CLICKHOUSE_ALLOW_WRITE_ACCESS": "false",
        "CLICKHOUSE_ALLOW_DROP": "false",
        "CLICKHOUSE_MCP_QUERY_TIMEOUT": str(QUERY_TIMEOUT_S),
    }


@asynccontextmanager
async def session() -> AsyncIterator[ClickHouseMCP]:
    """Start the official mcp-clickhouse server and talk to it over stdio.

    Per request rather than held open. The API scales to zero and a subprocess
    owned by an instance that may be stopped mid-query is a leak with a delay on
    it; starting one costs a few hundred milliseconds against a search that
    already waits on a model.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command="uvx",
        args=["--quiet", "mcp-clickhouse"],
        env=server_env(),
    )

    async with stdio_client(params) as (read, write), ClientSession(read, write) as mcp:
        await mcp.initialize()
        yield ClickHouseMCP(session=mcp)
