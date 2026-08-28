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

from fastapi import APIRouter, Depends, Query, Response

from ..services import analytics

log = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public"])

# Long enough that a burst of visitors costs one query, short enough that the
# page is visibly live. The claim is that these numbers come from production, so
# a stale hour would undermine the thing the page exists to demonstrate.
CACHE_SECONDS = 60


def _cached(response: Response) -> None:
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"


@router.get("/accuracy")
async def accuracy(response: Response) -> dict[str, Any]:
    """How often the system is right, defined precisely enough to publish.

        decision accuracy = confident decisions that stood / confident decisions

    Shots the system flagged for review are excluded from both sides. Those were
    handed to a person on purpose, and counting a human choosing between two
    near-identical takes as an error would be measuring the product working and
    calling it a fault.

    Nulls are returned rather than zeros when there is not enough data. A system
    with no measurements yet is not a system that is wrong every time, and the
    interface has to be able to tell those apart.
    """
    _cached(response)
    summary = await analytics.accuracy_summary()

    return {
        **summary,
        # Published alongside the number, because a figure whose definition
        # lives in a slide deck is not a figure anyone can check.
        "definition": (
            "Of the decisions the system made confidently, the share no editor "
            "later replaced. Shots it flagged for review are excluded — those "
            "were handed to a person deliberately."
        ),
        "caveat": (
            "Confident decisions are not systematically re-reviewed, so this is "
            "weaker evidence than a verified result. The evaluation set is the "
            "harder measure."
        ),
        # Stated in the payload, not only in the page, so it cannot be lost in a
        # rendering. Generated rows are excluded from this figure at the view
        # level: a number computed over them would measure the generator.
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
