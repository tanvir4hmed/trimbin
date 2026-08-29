"""Read-side queries for the public pages.

These run against ClickHouse directly rather than through MCP. MCP exists so an
agent can decide what to ask; these are fixed statements with no model involved,
and routing them through a tool-calling layer would add a hop and a failure mode
to queries that never vary.

Everything here is computed live. Precomputed nightly, the accuracy page would be
a report; computed on request, it is evidence — and a visitor can tell the
difference between a running system and a screenshot.
"""

from __future__ import annotations

import logging
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from ..config import settings

log = logging.getLogger(__name__)

_client: AsyncClient | None = None


class Waking(Exception):
    """The database is asleep and has not finished getting up.

    Distinct from a failure, and the distinction is the whole point. A visitor
    who arrives first after a quiet period has done nothing wrong, and telling
    them "something went wrong on our side" for a wait they simply have to sit
    through is the stuck-spinner failure this interface was written to avoid.
    """


async def client() -> AsyncClient:
    global _client
    if _client is not None:
        return _client

    try:
        _client = await clickhouse_connect.get_async_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            secure=True,
            query_limit=0,
            connect_timeout=90,
            # Generous on both, because the wait is not where the old comment
            # assumed it was.
            #
            # The service idles to keep costs down and takes tens of seconds to
            # wake. That happens during the client's own first statement — a
            # `SELECT version()` — which is governed by this timeout and not by
            # connect_timeout. Thirty seconds here meant the very first request
            # after a quiet period returned a 500 while the database was doing
            # exactly what it was configured to do.
            #
            # The cost of the generous value is that a genuinely slow query now
            # waits longer before failing. That is the better trade: a slow
            # query is rare and a cold start is most visits.
            send_receive_timeout=150,
        )
    except Exception as exc:
        # Leave nothing half-built. A client that failed to initialise is not
        # usable, and caching it would make one cold start into a permanent
        # outage until the instance is replaced.
        _client = None
        log.warning("could not reach the archive: %s", exc)
        raise Waking("The archive is waking up.") from exc

    return _client


async def _one(sql: str, params: dict | None = None) -> dict[str, Any]:
    """A single row, or an empty dict.

    An empty dict rather than an exception when there is no data: an archive
    with nothing in it is a legitimate state on a fresh deployment, and the
    pages are built to say so.
    """
    result = await (await client()).query(sql, parameters=params or {})
    if not result.result_rows:
        return {}
    return dict(zip(result.column_names, result.result_rows[0], strict=True))


async def _many(sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    result = await (await client()).query(sql, parameters=params or {})
    return [
        dict(zip(result.column_names, row, strict=True)) for row in result.result_rows
    ]


async def accuracy_summary() -> dict[str, Any]:
    """The headline number and the parts it is made of.

    The view carries the definition; this only reads it. Keeping the arithmetic
    in SQL means the number the page shows and the number anyone can reproduce
    against the database are the same number.
    """
    row = await _one("SELECT * FROM accuracy")

    if not row or not row.get("shots_total"):
        # Nulls, not zeros. A system with no measurements is not a system that
        # is wrong every time, and the interface must be able to say so.
        return {
            "decision_accuracy_pct": None,
            "confident_decisions": 0,
            "confident_overturned": 0,
            "flagged_for_review": 0,
            "flagged_changed_pct": None,
            "auto_decided_pct": None,
            "shots_total": 0,
        }

    return row


async def accuracy_by_project() -> list[dict[str, Any]]:
    """The same figure, per production.

    One number across every project is the wrong shape. Accuracy on a scene of
    locked-off interiors and accuracy on a handheld chase are different claims,
    and an editor asking how well this works on their footage cannot be answered
    by a mean over somebody else's.

    Joined to the corpus counts because a percentage without them is unreadable:
    four shots and four hundred both produce one, and only one of them means
    anything.
    """
    return await _many(
        """
        SELECT
            c.project_id                    AS project_id,
            a.decision_accuracy_pct         AS decision_accuracy_pct,
            a.confident_decisions           AS confident_decisions,
            a.confident_overturned          AS confident_overturned,
            a.flagged_for_review            AS flagged_for_review,
            a.flagged_changed_pct           AS flagged_changed_pct,
            a.auto_decided_pct              AS auto_decided_pct,
            a.shots_total                   AS shots_total,
            c.clips                         AS clips,
            c.scenes                        AS scenes,
            c.shots                         AS shots,
            c.unusable                      AS unusable,
            c.footage_hours                 AS footage_hours
        FROM project_corpus AS c
        LEFT JOIN accuracy_by_project AS a ON a.project_id = c.project_id
        ORDER BY c.project_id
        """
    )


async def eval_summary() -> list[dict[str, Any]]:
    """Per-axis results from the planted-fault set. Empty until it has run."""
    return await _many("SELECT * FROM eval_accuracy")


async def corpus() -> dict[str, Any]:
    """What the archive holds, counted as two separate things.

    Real footage and generated rows are never added together. The synthetic
    corpus is worth publishing — it is the reason to believe the engine choice —
    but only as what it is. A combined total would let a reader take the size of
    the generated set as evidence about the system, which is precisely the
    inference this separation exists to prevent.
    """
    row = await _one("SELECT * FROM corpus")
    if not row:
        return {
            "real_clips": 0, "synthetic_clips": 0,
            "real_productions": 0, "synthetic_productions": 0,
            "real_scenes": 0, "real_shots": 0,
            "real_hours": 0.0, "synthetic_hours": 0.0,
        }
    return row


# Below this many occurrences, a percentage is noise wearing a number's
# clothes. One disagreement out of two is 50% and describes nothing.
MIN_SAMPLE_FOR_A_RATE = 20


async def decision_count() -> int:
    """How many real decisions every figure on the accuracy page rests on.

    Published beside the figures rather than left implicit. A disagreement rate
    over thirty decisions and one over thirty thousand are different claims, and
    a reader who cannot see which they are looking at cannot weigh either.
    """
    row = await _one("SELECT count() AS n FROM real_decisions")
    return int(row.get("n", 0)) if row else 0


async def rejection_reasons(limit: int) -> list[dict[str, Any]]:
    """Why the system passed takes over, and how often a person disagreed.

    The disagreement rate per reason is the early warning: a reason editors
    routinely overrule is one the system should stop trusting, and it shows up
    here before anyone thinks to look.
    """
    return await _many(
        """
        WITH overruled AS (
            SELECT DISTINCT project_id, group_id, subgroup_id
            FROM real_decisions
            WHERE decided_by = 'human'
        )
        SELECT
            d.reason_code                                        AS reason_code,
            any(d.reason)                                        AS example,
            count()                                              AS occurrences,
            -- Null rather than a percentage below a handful of occurrences.
            -- One disagreement out of two reads as 50% and means nothing, and a
            -- figure that means nothing is worse on a page about accuracy than
            -- no figure at all.
            if(count() >= {min_sample:UInt16},
               round(100 * countIf(o.project_id != 0) / count(), 1),
               NULL)                                             AS disagreement_pct
        FROM real_decisions AS d
        LEFT JOIN overruled AS o
            ON  d.project_id  = o.project_id
            AND d.group_id    = o.group_id
            AND d.subgroup_id = o.subgroup_id
        WHERE d.outcome != 'selected' AND d.decided_by = 'agent'
        GROUP BY d.reason_code
        ORDER BY occurrences DESC
        LIMIT {limit:UInt8}
        """,
        {"limit": limit, "min_sample": MIN_SAMPLE_FOR_A_RATE},
    )


async def override_reasons(limit: int) -> list[dict[str, Any]]:
    """What editors say when they overrule the system.

    The half of the archive no public dataset contains. Every row is an
    editorial judgement paired with the reason a person gave for it, which is
    precisely the data that has never been recorded anywhere — and the reason no
    model can be trained to make these calls today.
    """
    return await _many(
        """
        SELECT
            reason,
            count()                 AS times,
            countDistinct(actor_id) AS editors
        FROM real_decisions
        WHERE decided_by = 'human'
        GROUP BY reason
        ORDER BY times DESC
        LIMIT {limit:UInt8}
        """,
        {"limit": limit},
    )


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
