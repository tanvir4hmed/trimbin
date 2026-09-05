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
    # A named finding already owns an exact evidence range. Do not search the
    # whole decision and then attach its editorial in/out points: that produced
    # an answer saying 0-16s beside a player link for the entire 65s take.
    if plan.get("finding"):
        return await _run_findings(project_id, plan)

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

    # No `has_decision` guard here, and none is possible: this query reads
    # `FROM decisions AS d`, so `d` is the table itself and a row cannot be
    # absent. The guard belongs to the queries that LEFT JOIN `latest_decision`,
    # where a missing right-hand side would otherwise default its Enum to the
    # first value and invent an outcome. Adding it here names a column that
    # does not exist, and ClickHouse rejects the whole query — which took
    # search down in production while every unit test passed.
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


async def _run_findings(
    project_id: int,
    plan: dict[str, Any],
) -> tuple[list[dict], str, int]:
    """Return the human-current finding itself as the playable evidence."""
    conditions = [
        "f.project_id = {project_id:UInt32}",
        "f.code = {finding:String}",
    ]
    params: dict[str, Any] = {
        "project_id": project_id,
        "finding": _code_value(plan["finding"]),
        "limit": min(int(plan.get("limit", 20)), HARD_LIMIT),
    }
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

    sql = f"""
        WITH latest_decision AS
        (
            SELECT clip_id,
                   toUInt8(1) AS has_decision,
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
            toString(f.clip_id) AS clip_id,
            c.group_id AS scene,
            c.subgroup_id AS setup,
            c.take_no AS take_no,
            if(d.has_decision = 1, toString(d.outcome), 'analysed') AS outcome,
            f.detail AS reason,
            'finding.match' AS reason_code,
            if(d.has_decision = 1, toString(d.decided_by), '') AS decided_by,
            if(d.has_decision = 1, d.actor, '') AS actor,
            if(d.has_decision = 1, d.score, 0) AS score,
            [f.code] AS finding_codes,
            [f.start_s] AS finding_starts_s,
            round(c.duration_ms / 1000, 2) AS duration_s,
            c.proxy_uri AS proxy_uri,
            f.start_s AS usable_from_s,
            f.end_s AS usable_to_s,
            1 AS relevance
        FROM current_findings AS f
        INNER JOIN current_clip_placement AS c
            ON c.project_id = f.project_id AND c.clip_id = f.clip_id
        LEFT JOIN latest_decision AS d ON d.clip_id = f.clip_id
        WHERE {" AND ".join(conditions)}
        ORDER BY f.start_s, c.take_no
        LIMIT {{limit:UInt16}}
    """
    rows, elapsed_ms = await _execute(sql, params, project_id)
    return rows, _readable(sql), elapsed_ms


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
        conditions.append("d.has_decision = 1")
        conditions.append("d.outcome = {outcome:String}")
        params["outcome"] = str(plan["outcome"])
    if plan.get("decided_by"):
        conditions.append("d.has_decision = 1")
        conditions.append("d.decided_by = {decided_by:String}")
        params["decided_by"] = str(plan["decided_by"])
    if plan.get("finding"):
        conditions.append(
            "s.clip_id IN (SELECT clip_id FROM current_findings "
            "WHERE project_id = {project_id:UInt32} AND code = {finding:String})"
        )
        params["finding"] = _code_value(plan["finding"])

    text = str(plan.get("text") or plan.get("semantic") or "").strip()
    if text:
        params["text"] = text
        # With an embedding this is fused retrieval, not a literal-text gate.
        # Requiring the same words first made semantic search incapable of
        # finding a paraphrase. Without an embedding, literal matching remains
        # the honest boundary.
        if not embedding:
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
                   toUInt8(1) AS has_decision,
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
            if(d.has_decision = 1, toString(d.outcome), 'analysed') AS outcome,
            s.description AS reason,
            'segment.match' AS reason_code,
            if(d.has_decision = 1, toString(d.decided_by), '') AS decided_by,
            if(d.has_decision = 1, d.actor, '') AS actor,
            if(d.has_decision = 1, d.score, 0) AS score,
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

    # A processing segment may be sixty seconds long; a current finding is an
    # event-level span.  Natural text that names the finding must seek to that
    # tight evidence instead of the containing analysis window.
    evidence_sql = ""
    exact_rows: list[dict] = []
    if text:
        scope = ["f.project_id = {project_id:UInt32}"]
        if plan.get("scene") is not None:
            scope.append("c.group_id = {scene:UInt32}")
        if plan.get("setup") is not None:
            scope.append("c.subgroup_id = {setup:UInt32}")
        if plan.get("take") is not None:
            scope.append("c.take_no = {take:UInt16}")
        if plan.get("outcome"):
            scope.extend(["d.has_decision = 1", "d.outcome = {outcome:String}"])
        if plan.get("decided_by"):
            scope.extend(["d.has_decision = 1", "d.decided_by = {decided_by:String}"])
        scope.append("positionCaseInsensitive(f.detail, {text:String}) > 0")
        finding_sql = f"""
            WITH latest_decision AS
            (
                SELECT clip_id, toUInt8(1) AS has_decision,
                       argMax(outcome, decided_at) AS outcome,
                       argMax(decided_by, decided_at) AS decided_by,
                       argMax(actor_id, decided_at) AS actor,
                       argMax(score, decided_at) AS score
                FROM decisions
                WHERE project_id = {{project_id:UInt32}}
                GROUP BY clip_id
            )
            SELECT
                toString(f.clip_id) AS clip_id,
                c.group_id AS scene,
                c.subgroup_id AS setup,
                c.take_no AS take_no,
                if(d.has_decision = 1, toString(d.outcome), 'analysed') AS outcome,
                f.detail AS reason,
                'finding.text' AS reason_code,
                if(d.has_decision = 1, toString(d.decided_by), '') AS decided_by,
                if(d.has_decision = 1, d.actor, '') AS actor,
                if(d.has_decision = 1, d.score, 0) AS score,
                [f.code] AS finding_codes,
                [f.start_s] AS finding_starts_s,
                round(c.duration_ms / 1000, 2) AS duration_s,
                c.proxy_uri AS proxy_uri,
                f.start_s AS usable_from_s,
                f.end_s AS usable_to_s,
                2 AS relevance
            FROM current_findings AS f
            INNER JOIN current_clip_placement AS c
                ON c.project_id = f.project_id AND c.clip_id = f.clip_id
            LEFT JOIN latest_decision AS d ON d.clip_id = f.clip_id
            WHERE {" AND ".join(scope)}
            ORDER BY (f.end_s - f.start_s), f.start_s
            LIMIT {{limit:UInt16}}
        """
        finding_rows, finding_ms = await _execute(finding_sql, params, project_id)
        elapsed_ms += finding_ms
        exact_rows.extend(finding_rows)
        evidence_sql = "\n\n-- Exact current finding evidence\n" + _readable(finding_sql)

    moment_scope = ["m.project_id = {project_id:UInt32}"]
    if plan.get("scene") is not None:
        moment_scope.append("c.group_id = {scene:UInt32}")
    if plan.get("setup") is not None:
        moment_scope.append("c.subgroup_id = {setup:UInt32}")
    if plan.get("take") is not None:
        moment_scope.append("c.take_no = {take:UInt16}")
    if plan.get("outcome"):
        moment_scope.extend(["d.has_decision = 1", "d.outcome = {outcome:String}"])
    if plan.get("decided_by"):
        moment_scope.extend(["d.has_decision = 1", "d.decided_by = {decided_by:String}"])
    if text and not embedding:
        moment_scope.append("positionCaseInsensitive(m.text, {text:String}) > 0")
    moment_scores: list[str] = []
    if text:
        moment_scores.append("3 * if(positionCaseInsensitive(m.text, {text:String}) > 0, 1, 0)")
    if embedding:
        moment_scores.append(
            f"{SEMANTIC_WEIGHT} * (1 - cosineDistance(m.embedding, {{vec:Array(Float32)}}))"
        )
    moment_relevance = " + ".join(moment_scores) if moment_scores else "1"
    moment_sql = f"""
        WITH latest_decision AS
        (
            SELECT clip_id, toUInt8(1) AS has_decision,
                   argMax(outcome, decided_at) AS outcome,
                   argMax(decided_by, decided_at) AS decided_by,
                   argMax(actor_id, decided_at) AS actor,
                   argMax(score, decided_at) AS score
            FROM decisions
            WHERE project_id = {{project_id:UInt32}}
            GROUP BY clip_id
        )
        SELECT
            toString(m.clip_id) AS clip_id,
            c.group_id AS scene,
            c.subgroup_id AS setup,
            c.take_no AS take_no,
            if(d.has_decision = 1, toString(d.outcome), 'analysed') AS outcome,
            m.text AS reason,
            concat('moment.', m.kind) AS reason_code,
            if(d.has_decision = 1, toString(d.decided_by), '') AS decided_by,
            if(d.has_decision = 1, d.actor, '') AS actor,
            if(d.has_decision = 1, d.score, 0) AS score,
            [concat('moment.', m.kind)] AS finding_codes,
            [m.start_s] AS finding_starts_s,
            round(c.duration_ms / 1000, 2) AS duration_s,
            c.proxy_uri AS proxy_uri,
            m.start_s AS usable_from_s,
            m.end_s AS usable_to_s,
            {moment_relevance} AS relevance
        FROM current_clip_moments AS m
        INNER JOIN current_clip_placement AS c
            ON c.project_id = m.project_id AND c.clip_id = m.clip_id
        LEFT JOIN latest_decision AS d ON d.clip_id = m.clip_id
        WHERE {" AND ".join(moment_scope)}
        ORDER BY relevance DESC, (m.end_s - m.start_s), m.start_s
        LIMIT {{limit:UInt16}}
    """
    moment_rows, moment_ms = await _execute(moment_sql, params, project_id)
    elapsed_ms += moment_ms
    exact_rows = moment_rows + exact_rows
    seen: set[tuple] = set()
    combined = []
    for row in [*exact_rows, *rows]:
        key = (row["clip_id"], row["usable_from_s"], row["usable_to_s"])
        if key in seen:
            continue
        seen.add(key)
        combined.append(row)
    rows = combined[: int(params["limit"])]
    evidence_sql += "\n\n-- Exact action/dialogue moments\n" + _readable(moment_sql)
    return rows, _readable(sql) + evidence_sql, elapsed_ms


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
    # A named finding is evidence and is never removed. Free-text memory can be
    # approximate, but a widened result remains labelled as widened.
    for field in ("text", "take", "setup"):
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
