"""Whether a shot needs a person, decided once.

This rule was implemented four times: the dot in the project tree, the reason in
the dashboard queue, the unconfirmed flag on the scene assembly, and the
needs_review field returned by a comparison. They read the same threshold and
then disagreed about everything else — the assembly ignored the circled take,
the comparison ignored whether anyone had looked, and only two of the four knew
that a person marking a shot approved ends the matter.

Four answers to one question is not a rounding error. A lead editor reading
"3 decided, 1 needs review" on the scene page and a different count on the
dashboard has no way to know which is true, and neither did I.

So the rule lives here, once, and everything reads it. The threshold still comes
from the agents package, because the panel and the interface must agree on what
"close" means or the queue and the archive describe different work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal[
    "too_few_takes",
    "not_judged",
    "differs_from_circle",
    "needs_review",
    "decided",
    "confirmed",
]

# What a person may set, mirrored from services/shots.py. Only `approved` and
# `in_progress` change this rule; the others are informational.
APPROVED = "approved"
IN_PROGRESS = "in_progress"


def review_margin() -> float:
    """Below this gap between first and second place, a person should look.

    Imported from the agents package rather than restated, so the panel that
    produces the margin and the interface that acts on it cannot drift.
    """
    from trimbin_agents.config import settings as agent_settings

    return agent_settings.review_margin


@dataclass(frozen=True)
class Assessment:
    """One shot, judged for the interface.

    `status` is the dot in the tree. `waiting_reason` is the sentence in the
    queue, or None when nobody is needed. They are produced together because
    they are the same decision seen from two screens — computing them apart is
    what let them disagree.
    """

    status: Status
    waiting_reason: str | None

    @property
    def needs_a_person(self) -> bool:
        return self.waiting_reason is not None


def assess(
    *,
    takes: int,
    has_verdict: bool,
    confirmed: bool,
    margin: float,
    circled_take: int = 0,
    chosen_take: int = 0,
    state: str = "",
    segments: int = 0,
    threshold: float | None = None,
) -> Assessment:
    """The one rule.

    Order matters, and it is ordered by what a person adds rather than by what
    is cheapest to check:

    1. A person who marked it approved has ended it, whatever the margin says.
       A set status is a claim by somebody with a name; a derived one is a claim
       about the system's confidence, and the first outranks the second.
    2. A person who has chosen at least one source range for this shot has also
       ended it — the same kind of claim as (1), by the same kind of person.
       This used to not exist, and it was wrong in two directions at once: a
       one-take shot with a chosen range reported "too few takes" forever,
       because nothing here knew a shot could be settled without a comparison;
       and a many-take shot chosen without running the panel reported "not
       compared yet" for a choice that had already been made.
    3. A shot with one take has nothing to *compare* — but it still has
       something to *decide*, now that a range can be chosen and trimmed from
       a single take. Before multi-select coverage existed this really was
       nothing but a fact, and the queue skipped it outright; it no longer is.
    4. A shot nothing has compared needs the comparison run.
    5. A shot where the room circled a different take than the measurements
       chose needs a person whether or not the call was close — the circle knows
       about performance, which this system deliberately never judges.
    6. Somebody already working on it is shown, not hidden, so a second editor
       does not start the same shot.
    7. A confirmed shot is done.
    8. A close call needs a person.

    Keyword-only, because several of these are booleans and integers in a row
    and a positional call site is one transposition away from being confidently
    wrong.
    """
    limit = review_margin() if threshold is None else threshold

    if state == APPROVED:
        return Assessment("confirmed", None)

    if segments > 0:
        return Assessment("confirmed", None)

    if takes < 2:
        if state == IN_PROGRESS:
            return Assessment("too_few_takes", "someone is on it")
        return Assessment("too_few_takes", "choose a range to use")

    if not has_verdict:
        return Assessment("not_judged", "not compared yet")

    if circled_take and chosen_take and circled_take != chosen_take:
        return Assessment("differs_from_circle", f"director circled take {circled_take}")

    if state == IN_PROGRESS:
        return Assessment("decided", "someone is on it")

    if confirmed:
        return Assessment("confirmed", None)

    if margin < limit:
        return Assessment("needs_review", "close call")

    return Assessment("decided", None)
