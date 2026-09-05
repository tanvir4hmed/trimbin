"""Contracts for the Archivist.

The only agent a person talks to directly, and the only one on a latency budget
someone is actually waiting out.

The shape here is built around one rule: an empty answer must be expressible and
must be distinguishable from a failure. Those are different things — "there is
nothing like that in this project" is useful, "the search did not run" is a
problem, and a system that returns the same empty list for both teaches people to
stop trusting either.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from .base import Strict, TimeRange


class Scope(StrEnum):
    """How far a question is allowed to reach.

    Enforced in the query rather than in the prompt. A visitor asking politely to
    see another project should be unable to, not merely discouraged.
    """

    DEMO = "demo"  # the public project, no account
    PROJECT = "project"  # one project the caller belongs to


class Outcome(StrEnum):
    """What happened, told apart deliberately."""

    FOUND = "found"
    NO_MATCH = "no_match"  # searched, nothing matched
    WIDENED = "widened"  # nothing matched exactly, near misses returned
    NEEDS_CLARIFICATION = "needs_clarification"
    FAILED = "failed"  # the search did not run


class QueryRequest(Strict):
    question: str = Field(min_length=2, max_length=500)
    scope: Scope
    project_id: int | None = Field(
        default=None,
        description="Required for PROJECT scope; ignored for DEMO.",
    )

    @model_validator(mode="after")
    def _project_scope_needs_a_project(self) -> QueryRequest:
        if self.scope is Scope.PROJECT and self.project_id is None:
            raise ValueError("project scope requires a project_id")
        return self


class Match(Strict):
    """One result, carrying the context that makes it meaningful.

    A bare list of clip ids would be useless. What an editor needs is which shot
    it came from, what happened to it, and why — the answer to "why am I being
    shown this" has to arrive with the result rather than after another click.
    """

    clip_id: UUID
    group_id: int
    subgroup_id: int
    take_no: int

    duration_s: float
    description: str = Field(max_length=300)

    # Where playback should start, which is not where the event starts.
    #
    # Cutting in exactly on a line or an action gives an editor no run-up: by
    # the time they have registered what they are watching it has happened. A
    # second and a half of lead-in is how anyone reviews footage.
    #
    # Kept separate from `where` on purpose. The displayed range stays the true
    # span of the event, because widening that to be helpful would mean the
    # archive reporting a moment as longer than it was.
    play_from_s: float = Field(
        default=0.0, ge=0.0, description="Seek here; `where` still states the real span."
    )

    outcome: str = Field(description="What was decided about this take.")
    reason: str = Field(max_length=200, description="Why, in the words recorded at the time.")
    decided_by: str = Field(description="agent or a person's name.")

    playlist_uri: str = Field(default="", description="Plays in place.")
    where: TimeRange | None = Field(
        default=None,
        description="The moment this matched, when the question was about one.",
    )
    relevance: float = Field(ge=0, le=1)


class QueryResult(Strict):
    question: str
    outcome: Outcome
    matches: list[Match] = Field(default_factory=list)

    answer: str = Field(
        max_length=400,
        description="What to say to the person, in plain language.",
    )
    suggestion: str = Field(
        default="",
        max_length=200,
        description=(
            "Offered when nothing matched: a wider constraint worth trying. "
            "Never a consolation result presented as an answer."
        ),
    )

    sql: str = Field(
        default="",
        description=(
            "The query that ran. Shown in the interface so a result can be "
            "checked rather than trusted."
        ),
    )
    elapsed_ms: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _outcome_must_match_the_evidence(self) -> QueryResult:
        """The failure this prevents is a plausible answer with nothing behind it.

        An agent that says it found something and returns no matches has
        hallucinated, and the person will act on the sentence rather than the
        empty list. Making that state unrepresentable is cheaper than hoping.
        """
        if self.outcome is Outcome.FOUND and not self.matches:
            raise ValueError("outcome=found requires at least one match")
        if self.outcome is Outcome.NO_MATCH and self.matches:
            raise ValueError("outcome=no_match cannot carry matches")
        if self.outcome is Outcome.WIDENED and not self.matches:
            raise ValueError("outcome=widened requires the near misses it widened to")
        return self
