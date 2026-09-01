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

There is no direct-client fallback. If the official read-only MCP path cannot
run, the API reports search unavailable. An outage and an empty archive are
different facts, and silently bypassing the declared runtime boundary would make
the public evidence endpoint untrue.
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)


class SearchUnavailable(RuntimeError):
    """The official read-only MCP path did not answer; never a false empty."""


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
    "clip_id",
    "scene",
    "setup",
    "take_no",
    "outcome",
    "reason",
    "reason_code",
    "decided_by",
    "actor",
    "score",
    "finding_codes",
    "finding_starts_s",
    "duration_s",
    "proxy_uri",
    "usable_from_s",
    "usable_to_s",
    "relevance",
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
    # Descriptions and semantic intent belong to moments, not whole decision
    # rows. A result therefore carries the segment's exact playable range.
    if plan.get("text") or plan.get("semantic") or embedding:
        return await _run_moments(project_id, plan, embedding)

    conditions = ["d.project_id = {project_id:UInt32}"]
    params: dict[str, Any] = {"project_id": project_id}

    if plan.get("scene") is not None:
        conditions.append("c.group_id = {scene:UInt32}")
        params["scene"] = int(plan["scene"])

    if plan.get("setup") is not None:
        conditions.append("c.subgroup_id = {setup:UInt32}")
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
        conditions.append(
            "d.clip_id IN (SELECT clip_id FROM current_findings "
            "WHERE project_id = {project_id:UInt32} AND code = {finding:String})"
        )
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
            f"{TEXT_WEIGHT} * (positionCaseInsensitive(d.reason, {{text:String}}) > 0 ? 1 : 0.6)"
        )
    if embedding:
        score_parts.append(
            f"{SEMANTIC_WEIGHT} * (1 - cosineDistance(c.embedding, {{vec:Array(Float32)}}))"
        )
        params["vec"] = embedding

    score = " + ".join(score_parts) if score_parts else "1"

    order = "relevance DESC, d.decided_at " + ("DESC" if plan.get("newest_first", True) else "ASC")
    limit = min(int(plan.get("limit", 20)), HARD_LIMIT)
    params["limit"] = limit

    sql = f"""
        SELECT
            toString(d.clip_id)   AS clip_id,
            c.group_id            AS scene,
            c.subgroup_id         AS setup,
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
        INNER JOIN current_clip_placement AS c
            ON c.clip_id = d.clip_id AND c.project_id = d.project_id
        WHERE {" AND ".join(conditions)}
        ORDER BY {order}
        LIMIT 1 BY d.clip_id
        LIMIT {{limit:UInt16}}
    """

    rows, elapsed_ms = await _execute(sql, params, project_id)
    return rows, _readable(sql), elapsed_ms


async def _execute(sql: str, params: dict[str, Any], project_id: int) -> tuple[list[dict], int]:
    """Run only through the official read-only MCP path, and fail closed."""
    import time

    started = time.perf_counter()

    try:
        from trimbin_agents.tools.clickhouse_mcp import ReaderMissing, session

        async with session() as mcp:
            outcome = await mcp.run_query(_interpolated(sql, params), project_id, columns=_COLUMNS)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log.info("search via MCP: %d rows in %dms", len(outcome.rows), elapsed_ms)
        return outcome.rows, elapsed_ms

    except ReaderMissing as exc:
        log.error("MCP not started: %s", exc)
        raise SearchUnavailable("The read-only ClickHouse MCP reader is not configured.") from exc
    except Exception as exc:
        log.exception("MCP query failed")
        raise SearchUnavailable("Archive search is temporarily unavailable.") from exc


async def _run_moments(
    project_id: int,
    plan: dict[str, Any],
    embedding: list[float] | None,
) -> tuple[list[dict], str, int]:
    """Search current analysis segments and return the exact playable span."""
    conditions = ["s.project_id = {project_id:UInt32}"]
    params: dict[str, Any] = {"project_id": project_id}
    if plan.get("scene") is not None:
        conditions.append("c.group_id = {scene:UInt32}")
        params["scene"] = int(plan["scene"])
    if plan.get("setup") is not None:
        conditions.append("c.subgroup_id = {setup:UInt32}")
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
        conditions.append(
            "s.clip_id IN (SELECT clip_id FROM current_findings "
            "WHERE project_id = {project_id:UInt32} AND code = {finding:String})"
        )
        params["finding"] = _code_value(plan["finding"])

    text = str(plan.get("text") or (plan.get("semantic") if not embedding else "") or "").strip()
    if text:
        params["text"] = text
        conditions.append(
            "(positionCaseInsensitive(s.description, {text:String}) > 0 "
            "OR positionCaseInsensitive(s.transcript, {text:String}) > 0 "
            "OR arrayExists(x -> positionCaseInsensitive(x, {text:String}) > 0, s.actions) "
            "OR arrayExists(x -> positionCaseInsensitive(x, {text:String}) > 0, s.objects) "
            "OR positionCaseInsensitive(d.reason, {text:String}) > 0)"
        )

    score_parts: list[str] = []
    if text:
        score_parts.append(
            f"{TEXT_WEIGHT} * "
            "(positionCaseInsensitive(s.description, {text:String}) > 0 ? 1 : 0.75)"
        )
    if embedding:
        params["vec"] = embedding
        score_parts.append(
            f"{SEMANTIC_WEIGHT} * (1 - cosineDistance(s.embedding, {{vec:Array(Float32)}}))"
        )
    relevance = " + ".join(score_parts) if score_parts else "1"
    params["limit"] = min(int(plan.get("limit", 20)), HARD_LIMIT)

    sql = f"""
        WITH latest_decision AS
        (
            SELECT clip_id,
                   argMax(outcome, decided_at) AS outcome,
                   argMax(reason, decided_at) AS reason,
                   argMax(decided_by, decided_at) AS decided_by,
                   argMax(actor_id, decided_at) AS actor,
                   argMax(score, decided_at) AS score
            FROM decisions
            WHERE project_id = {{project_id:UInt32}}
            GROUP BY clip_id
        )
        SELECT
            toString(s.clip_id) AS clip_id,
            c.group_id AS scene,
            c.subgroup_id AS setup,
            c.take_no AS take_no,
            ifNull(d.outcome, 'analysed') AS outcome,
            s.description AS reason,
            'segment.match' AS reason_code,
            ifNull(d.decided_by, 'agent') AS decided_by,
            ifNull(d.actor, '') AS actor,
            ifNull(d.score, 0) AS score,
            ['segment.match'] AS finding_codes,
            [s.start_s] AS finding_starts_s,
            round(c.duration_ms / 1000, 2) AS duration_s,
            c.proxy_uri AS proxy_uri,
            s.start_s AS usable_from_s,
            s.end_s AS usable_to_s,
            {relevance} AS relevance
        FROM current_clip_segments AS s
        INNER JOIN current_clip_placement AS c
            ON c.project_id = s.project_id AND c.clip_id = s.clip_id
        LEFT JOIN latest_decision AS d ON d.clip_id = s.clip_id
        WHERE {" AND ".join(conditions)}
        ORDER BY relevance DESC, s.start_s
        LIMIT {{limit:UInt16}}
    """
    rows, elapsed_ms = await _execute(sql, params, project_id)
    return rows, _readable(sql), elapsed_ms


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
