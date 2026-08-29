"""Hybrid retrieval over the archive: what was decided, and why.

Three ways of matching, in one query.

**Structured** — scene, setup, outcome, who decided, which finding. Exact, and
what most real questions turn out to be.

**Text** — the words people actually wrote. An editor searching for "boom" wants
the take whose reason says boom, not one that merely looks like it might.

**Semantic** — the clip embedding, for questions about the picture rather than
about anything anyone wrote. Weakest of the three and used accordingly; the
misplacement eval showed that within one production every clip resembles every
other, so this narrows and never decides.

Two things are true at once here and it is worth separating them.

**The statement is built by us**, from parameters the model chose. The model does
not write SQL. That was a response to finding the MCP wrapper's safety check
resting on a keyword regex beside a comment claiming a read-only user existed —
it did not.

**The statement is executed through the official `mcp-clickhouse` server**, as
the ClickHouse track requires the database to be used at runtime, and the
read-only user the comment described now exists: SELECT on ten named objects,
under a profile with `readonly = 1 CONST`.

Those are different questions. Who composes the statement is about correctness —
a fixed shape answers the questions people ask and cannot be talked into
answering others. Who executes it, and as whom, is about blast radius. Doing
both properly costs nothing and the earlier version did neither.

The direct client remains as a fallback for one case: the MCP subprocess failing
to start. A search that cannot run should say so, but a search that falls back
to a path with the same guarantees is better than an error page — and the
guarantees are the same because the statement was already ours.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .analytics import client

log = logging.getLogger(__name__)

# Beyond this the result is a listing, not an answer. An editor scanning two
# hundred rows has been handed the problem back.
HARD_LIMIT = 100

# The shape of every statement this module builds, in order.
#
# Kept beside the SELECT it describes and passed to MCP, which returns positional
# rows with no usable header. Reading names out of the response instead is how a
# six-row result once became "nothing matched" — the parser looked for objects,
# found lists, and returned empty.
#
# It has to match the SELECT below. A mismatch mislabels every column, which is
# worse than an error, so the test suite asserts the two agree.
_COLUMNS = [
    "clip_id", "scene", "setup", "take_no", "outcome", "reason", "reason_code",
    "decided_by", "actor", "score", "finding_codes", "finding_starts_s",
    "duration_s", "proxy_uri", "usable_from_s", "usable_to_s", "relevance",
]

# How much a semantic match is worth beside an exact one.
#
# Deliberately small. Cosine similarity within one production sits between 0.91
# and 0.98 for everything — the misplacement eval measured that — so an
# unweighted score would rank every clip near the top and drown the rows that
# actually matched a word somebody wrote.
SEMANTIC_WEIGHT = 0.35
TEXT_WEIGHT = 1.0


async def run(
    project_id: int,
    plan: dict[str, Any],
    embedding: list[float] | None = None,
) -> tuple[list[dict], str, int]:
    """Search one project. Returns the rows, the SQL that ran, and how long.

    The SQL comes back so the interface can show it. A result somebody can check
    is worth more than one they have to trust, and this system's whole argument
    is that the reasoning should be visible.
    """
    conditions = ["d.project_id = {project_id:UInt32}"]
    params: dict[str, Any] = {"project_id": project_id}

    if plan.get("scene") is not None:
        conditions.append("d.group_id = {scene:UInt32}")
        params["scene"] = int(plan["scene"])

    if plan.get("setup") is not None:
        conditions.append("d.subgroup_id = {setup:UInt32}")
        params["setup"] = int(plan["setup"])

    if plan.get("take") is not None:
        conditions.append("c.take_no = {take:UInt16}")
        params["take"] = int(plan["take"])

    if plan.get("outcome"):
        conditions.append("d.outcome = {outcome:String}")
        params["outcome"] = str(plan["outcome"])

    if plan.get("decided_by"):
        conditions.append("d.decided_by = {decided_by:String}")
        params["decided_by"] = str(plan["decided_by"])

    if plan.get("finding"):
        conditions.append("has(d.finding_codes, {finding:String})")
        params["finding"] = _code_value(plan["finding"])

    text = (plan.get("text") or "").strip()
    if text:
        # Case-insensitive substring across everything a person wrote or a
        # board said. Not full-text ranking: the corpus is a production, not a
        # library, and an editor searching "boom" wants the rows containing
        # boom rather than the ones a scorer thinks are most about booms.
        conditions.append(
            "(positionCaseInsensitive(d.reason, {text:String}) > 0"
            " OR positionCaseInsensitive(c.description, {text:String}) > 0"
            " OR positionCaseInsensitive(c.slate_raw, {text:String}) > 0"
            " OR arrayExists(x -> positionCaseInsensitive(x, {text:String}) > 0,"
            "                d.finding_codes))"
        )
        params["text"] = text

    # Relevance, assembled from whichever signals are present.
    score_parts = []
    if text:
        score_parts.append(
            f"{TEXT_WEIGHT} * "
            "(positionCaseInsensitive(d.reason, {text:String}) > 0 ? 1 : 0.6)"
        )
    if embedding:
        score_parts.append(
            f"{SEMANTIC_WEIGHT} * (1 - cosineDistance(c.embedding, {{vec:Array(Float32)}}))"
        )
        params["vec"] = embedding

    score = " + ".join(score_parts) if score_parts else "1"

    order = "relevance DESC, d.decided_at " + (
        "DESC" if plan.get("newest_first", True) else "ASC"
    )
    limit = min(int(plan.get("limit", 20)), HARD_LIMIT)
    params["limit"] = limit

    sql = f"""
        SELECT
            toString(d.clip_id)   AS clip_id,
            d.group_id            AS scene,
            d.subgroup_id         AS setup,
            c.take_no             AS take_no,
            d.outcome             AS outcome,
            d.reason              AS reason,
            d.reason_code         AS reason_code,
            d.decided_by          AS decided_by,
            d.actor_id            AS actor,
            round(d.score, 3)     AS score,
            d.finding_codes       AS finding_codes,
            d.finding_starts_s    AS finding_starts_s,
            round(c.duration_ms / 1000, 2) AS duration_s,
            c.proxy_uri           AS proxy_uri,
            d.in_point_s          AS usable_from_s,
            d.out_point_s         AS usable_to_s,
            {score}               AS relevance
        FROM decisions AS d
        INNER JOIN clips AS c
            ON c.clip_id = d.clip_id AND c.project_id = d.project_id
        WHERE {' AND '.join(conditions)}
        ORDER BY {order}
        LIMIT 1 BY d.clip_id
        LIMIT {{limit:UInt16}}
    """

    rows, elapsed_ms = await _execute(sql, params, project_id)
    return rows, _readable(sql), elapsed_ms


async def _execute(
    sql: str, params: dict[str, Any], project_id: int
) -> tuple[list[dict], int]:
    """Run the statement through MCP, falling back to the direct client.

    MCP first, because that is how this project is required to reach ClickHouse
    at runtime and because the reader user it connects as is a real boundary.
    The direct client is used only when the subprocess will not start.

    The fallback is honest rather than convenient: the statement is identical
    and was composed here either way, so nothing about what runs changes — only
    which connection carries it. It is logged, because a deployment silently
    never using MCP is exactly the kind of thing that goes unnoticed for weeks.
    """
    import time

    started = time.perf_counter()

    try:
        from trimbin_agents.tools.clickhouse_mcp import ReaderMissing, session

        async with session() as mcp:
            outcome = await mcp.run_query(
                _interpolated(sql, params), project_id, columns=_COLUMNS
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log.info("search via MCP: %d rows in %dms", len(outcome.rows), elapsed_ms)
        return outcome.rows, elapsed_ms

    except ReaderMissing as exc:
        log.error("MCP not started: %s", exc)
    except Exception:
        log.exception("MCP query failed; falling back to the direct client")

    ch = await client()
    started = time.perf_counter()
    result = await ch.query(sql, parameters=params)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    rows = [
        dict(zip(result.column_names, row, strict=True)) for row in result.result_rows
    ]
    log.info("search via the direct client: %d rows in %dms", len(rows), elapsed_ms)
    return rows, elapsed_ms


def _interpolated(sql: str, params: dict[str, Any]) -> str:
    """Substitute our own parameters, because MCP takes a statement not a binding.

    Safe only because every value here was produced by us or validated by a
    pydantic contract before it arrived: integers are cast, enums come from a
    closed taxonomy, and the one free-text field is escaped below.

    That is a narrower claim than "this escapes SQL properly", and the narrowness
    is the point. Nothing arbitrary reaches this function.
    """
    out = sql
    for name, value in params.items():
        if isinstance(value, bool):
            literal = "1" if value else "0"
        elif isinstance(value, int | float):
            literal = str(value)
        elif isinstance(value, list):
            literal = "[" + ",".join(str(float(v)) for v in value) + "]"
        else:
            literal = "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"

        # The placeholder carries its type, e.g. {text:String}.
        out = re.sub(r"\{" + re.escape(name) + r":[A-Za-z0-9()]+\}", literal, out)
    return out


async def widen(project_id: int, plan: dict[str, Any]) -> tuple[list[dict], str, int]:
    """Try again with the narrowest filter removed.

    Offered rather than substituted. A near miss presented as an answer is the
    failure this exists to avoid — the person asked about scene 12 and would act
    on rows from scene 9 without noticing.

    Text goes first because it is the filter most likely to be slightly wrong:
    an editor searching for a word they remember writing is often remembering it
    differently.
    """
    wider = dict(plan)
    for field in ("text", "take", "finding", "setup"):
        if wider.get(field):
            wider[field] = None if field != "text" else ""
            return await run(project_id, wider)

    return [], "", 0


def _code_value(code: Any) -> str:
    """The taxonomy string, whether an enum or already a string arrived."""
    return str(getattr(code, "value", code))


def _readable(sql: str) -> str:
    """Collapse the indentation so the interface can show it without a scrollbar."""
    return " ".join(sql.split())
