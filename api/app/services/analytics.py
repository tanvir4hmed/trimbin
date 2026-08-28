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


async def client() -> AsyncClient:
    global _client
    if _client is None:
        _client = await clickhouse_connect.get_async_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            secure=True,
            query_limit=0,
            # Generous on connect, tight on query.
            #
            # The service idles to keep costs down, and waking one takes tens of
            # seconds. That cost lands entirely on the first visitor after a
            # quiet period — which, for a demo nobody is hammering, is most
            # visitors. Timing out there would show an error to someone whose
            # only problem was arriving first.
            #
            # Once awake, a slow query is a real fault and should surface as one.
            connect_timeout=90,
            send_receive_timeout=30,
        )
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
