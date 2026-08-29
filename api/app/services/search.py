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

The query shape is fixed here and the model supplies only parameters. That is a
departure from the plan, which had the Archivist writing SQL through MCP — see
`contracts/search.py` for why, and for the comment that turned out to name a
protection nobody had built.
"""

from __future__ import annotations

import logging
from typing import Any

from .analytics import client

log = logging.getLogger(__name__)

# Beyond this the result is a listing, not an answer. An editor scanning two
# hundred rows has been handed the problem back.
HARD_LIMIT = 100

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

    ch = await client()
    import time

    started = time.perf_counter()
    result = await ch.query(sql, parameters=params)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    rows = [
        dict(zip(result.column_names, row, strict=True)) for row in result.result_rows
    ]
    log.info("search returned %d rows in %dms", len(rows), elapsed_ms)

    return rows, _readable(sql), elapsed_ms


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
