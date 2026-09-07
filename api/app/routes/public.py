"""The public surface: no account, no cost to us, nothing hidden.

Two audiences share these routes. Someone evaluating the system wants to know
whether it works and whether the claims hold; someone considering using it wants
the same thing. Both are served by publishing the error rate rather than
describing the features.

Everything here reads. Nothing here writes, and nothing here is rate-limited by
identity, because there is no identity — so the protection is that these queries
are cheap and their results are cacheable.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from ..config import settings
from ..services import analytics, members, quality

log = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public"])

# Long enough that a burst of visitors costs one query, short enough that the
# page is visibly live. The claim is that these numbers come from production, so
# a stale hour would undermine the thing the page exists to demonstrate.
CACHE_SECONDS = 60


def _cached(response: Response) -> None:
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"


@router.get("/mcp-evidence")
async def mcp_evidence(response: Response) -> dict[str, Any]:
    """Public, checkable statement of the runtime search boundary."""
    _cached(response)
    return {
        "runtime": "official mcp-clickhouse over stdio",
        "identity": "dedicated ClickHouse read-only user",
        "project_scoped": True,
        "direct_fallback": False,
        "configured": bool(settings.clickhouse_reader_user and settings.clickhouse_reader_password),
        "result_contract": "exact clip_id plus playable start_s/end_s",
    }


@router.get("/accuracy")
async def accuracy(response: Response) -> dict[str, Any]:
    """Explicit finding-review agreement across public, real-footage projects."""
    response.headers["Cache-Control"] = "no-store"
    report = await quality.report()
    return {
        **report.model_dump(mode="json"),
        "definition": (
            "First-review agreement = confirmed unchanged / explicitly reviewed findings. "
            "Corrected and dismissed findings are reviewed but not confirmed unchanged."
        ),
        "caveat": (
            "Unreviewed findings and take preferences are not correctness evidence. "
            "Self-selected reviews do not measure overall accuracy or missed issues."
        ),
        "counts_only_real_work": True,
    }


@router.get("/eval")
async def eval_results(response: Response) -> dict[str, Any]:
    """Accuracy against footage with faults planted deliberately.

    The harder number and the smaller sample. We know there is camera shake at
    4.2 seconds because we put it there, so a finding is a fact rather than an
    agreement.

    Missed faults and false alarms are reported separately and never summed. A
    missed problem reaches the cut; a false alarm costs an editor ten seconds.
    """
    _cached(response)
    rows = await analytics.eval_summary()

    if not rows:
        # Said plainly rather than shown as a hopeful zero.
        return {
            "state": "not_run",
            "message": "The evaluation has not been run against this deployment yet.",
            "axes": [],
        }

    return {"state": "measured", "axes": rows}


@router.get("/accuracy/by-project")
async def accuracy_per_project(response: Response) -> dict[str, Any]:
    """Compatibility entry point; private project counts are never published."""
    return await accuracy(response)


@router.get("/limits")
async def guest_limits(response: Response) -> dict[str, Any]:
    """What a guest account may hold, published before anyone signs up for one.

    Published rather than hard-coded into the page, so the numbers a visitor is
    shown and the numbers the API enforces are the same numbers. Two copies
    drift, and the drift shows up as a person being refused for exceeding a
    limit the page told them they were within.

    This used to describe a sandbox — a separate project with separate rules,
    reached by a separate page. That was the wrong shape: it sent a visitor
    somewhere the real users never go and then asked them to judge the thing
    they had not seen. The limits now sit on a project a guest actually owns, in
    the same interface everybody else uses.
    """
    _cached(response)
    limits = members.GUEST_LIMITS
    return {
        **limits.as_dict(),
        "note": (
            f"Sign in as a guest and you get a real workspace: "
            f"{limits.projects} projects of your own, {limits.scenes} scenes "
            f"each, up to {limits.takes_per_shot} takes a shot, clips up to "
            f"{limits.clip_seconds} seconds, kept for {limits.retention_days} "
            f"days. In our projects you can upload, review, comment, and "
            f"overrule any call we made. Editor-owned records stay protected "
            f"from guest deletion."
        ),
    }


@router.get("/scale")
async def scale(response: Response) -> dict[str, Any]:
    """What the archive holds, real and generated counted apart.

    Present because the accuracy figure means something different over a
    thousand decisions than over three hundred thousand, and a visitor cannot
    weigh one without the other.

    The two are never summed. The generated corpus exists to show the queries
    stay fast at scale and is evidence of nothing else; adding it to the real
    total would invite exactly the inference it cannot support.
    """
    _cached(response)
    counts = await analytics.corpus()

    return {
        "real": {
            "productions": counts["real_productions"],
            "clips": counts["real_clips"],
            "scenes": counts["real_scenes"],
            "shots": counts["real_shots"],
            "footage_hours": counts["real_hours"],
        },
        "synthetic": {
            "productions": counts["synthetic_productions"],
            "clips": counts["synthetic_clips"],
            "footage_hours": counts["synthetic_hours"],
            "purpose": (
                "Generated to demonstrate that queries stay fast over millions "
                "of rows. Excluded from every accuracy figure on this site."
            ),
        },
    }


@router.get("/reasons")
async def reasons(
    response: Response,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> dict[str, Any]:
    """Why takes lose, and how often a human overruled each reason.

    The disagreement column is the useful one. A reason editors routinely
    overrule is a reason the system should stop trusting, and this is where that
    becomes visible long before anyone thinks to look for it.
    """
    _cached(response)
    total = await analytics.decision_count()

    return {
        # What everything below rests on, stated rather than left to be
        # inferred. These queries used to read the whole decisions table, which
        # holds three hundred thousand generated rows against a few dozen real
        # ones, so the published figures were a report about a fixture. They now
        # read a view that cannot include them — and this number is how a reader
        # sees for themselves how thin the real archive still is.
        "decisions_counted": total,
        "basis": (
            "Real footage only. Generated rows are excluded at the view, not by "
            "a filter someone has to remember to write."
        ),
        "agent": await analytics.rejection_reasons(limit),
        # The half no public dataset contains: an editorial judgement paired
        # with the reason a person gave for it.
        "human": await analytics.override_reasons(limit),
    }


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness only.

    Deliberately does not touch the database. A health check that fails when a
    dependency is slow takes the service down for a problem it could have
    survived, and the dependency has its own monitoring.
    """
    return {"status": "ok"}
