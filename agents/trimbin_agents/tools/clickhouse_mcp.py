"""The ClickHouse MCP client, read-only by contract.

`CLICKHOUSE_ALLOW_WRITE_ACCESS` stays false and this module never sets it. A
language model with write access to a production database is one prompt injection
away from a destructive query, and the input here is a question typed by a person
plus footage a camera was pointed at — both untrusted by definition.

Writes go through the typed service layer instead, where a schema decides what is
legal. The requirement to use MCP at runtime is met the way it should be: every
search an editor runs goes through this.

Defence in depth, because a read-only server is one flag away from not being one:

  * the connection is opened with a read-only user
  * the statement is checked before it is sent
  * the scope filter is applied by us, not asked for in the prompt
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)

# Rejected before anything reaches the server. Not the primary defence — the
# read-only user is — but the one that produces a legible error instead of a
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

    async def run_query(self, sql: str, project_id: int | None) -> QueryOutcome:
        assert_read_only(sql)
        scope = scope_clause(project_id)

        if scope not in sql:
            raise UnsafeQuery("query is not scoped to the caller's project")

        limited = self._with_limit(sql)
        started = time.perf_counter()

        try:
            result = await self._session.call_tool(
                "run_query", {"query": limited}
            )
        except Exception as exc:  # noqa: BLE001
            raise QueryFailed(str(exc)) from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        rows = _rows_from(result)

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


def _rows_from(result: Any) -> list[dict[str, Any]]:
    """Unwrap whatever shape the MCP response arrived in.

    Tolerant on purpose: the transport is not the interesting part, and a
    structural surprise here should not read as a failed search.
    """
    content = getattr(result, "content", result)
    if isinstance(content, list) and content and hasattr(content[0], "text"):
        import json

        try:
            parsed = json.loads(content[0].text)
        except (ValueError, AttributeError):
            return []
        content = parsed

    if isinstance(content, dict):
        content = content.get("rows", content.get("data", []))

    return [r for r in content if isinstance(r, dict)] if isinstance(content, list) else []


def server_env() -> dict[str, str]:
    """Environment for the MCP server process.

    The write flags are set to false explicitly rather than left to the default.
    A default is a decision someone else made and can change; this one is ours
    and is visible in the code.
    """
    return {
        "CLICKHOUSE_HOST": settings.clickhouse_url,
        "CLICKHOUSE_USER": settings.clickhouse_user,
        "CLICKHOUSE_PASSWORD": settings.clickhouse_password,
        "CLICKHOUSE_ALLOW_WRITE_ACCESS": "false",
        "CLICKHOUSE_ALLOW_DROP": "false",
        "CLICKHOUSE_MCP_QUERY_TIMEOUT": str(QUERY_TIMEOUT_S),
    }
