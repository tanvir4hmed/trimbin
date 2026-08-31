"""What a question becomes before it touches the database.

The model turns plain language into this, and this is what runs. It does not
write SQL.

That is a deliberate departure from the plan, which said the Archivist would
query through an MCP session. The wrapper for that exists and its safety check
carries a comment naming a read-only database user as the primary defence —
there is no such user. The connection is the admin one, and the only thing
between a model and the production archive was a regular expression matching
keywords.

A regex over SQL is a filter, not a boundary. `SELECT` with a subquery, a
comment splicing a keyword, a function name that happens to contain a forbidden
word: all of these are ordinary SQL and none of them are what the pattern was
written for.

So the shape of every query is fixed in code and the model chooses only its
parameters. That answers the questions people actually ask — "which takes had a
continuity problem", "what did we reject in scene 12", "find the handheld ones"
— and removes the class of risk rather than filtering it.

The cost is real and worth naming: a question no filter here expresses cannot be
answered, and the honest response is to say so rather than to approximate.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .base import FindingCode, Strict


class SearchPlan(Strict):
    """A question, expressed as filters over the archive.

    Every field is optional and an empty plan is legal: it means "everything in
    this project", which is a reasonable reading of "show me what we have".
    """

    # -- what kind of thing to look for -------------------------------------
    text: str = Field(
        default="",
        max_length=200,
        description=(
            "Words to look for in the recorded reasons, descriptions and slates. "
            "The editor's own language, not a paraphrase of the question."
        ),
    )
    semantic: str = Field(
        default="",
        max_length=200,
        description=(
            "A description of what the footage looks like, for comparison "
            "against the clip embeddings. Use when the question is about the "
            "image rather than about words anybody wrote."
        ),
    )

    # -- structured filters --------------------------------------------------
    scene: int | None = Field(default=None, ge=0, description="Scene number.")
    setup: int | None = Field(default=None, ge=0, description="Shot or setup number.")
    take: int | None = Field(default=None, ge=0)

    outcome: str | None = Field(
        default=None,
        description="selected, runner_up, not_selected or unusable.",
    )
    decided_by: str | None = Field(
        default=None,
        description="agent or human. Use human for questions about overrides.",
    )
    finding: FindingCode | None = Field(
        default=None,
        description="Restrict to takes carrying this finding.",
    )

    # -- ordering and size ---------------------------------------------------
    newest_first: bool = Field(
        default=True,
        description="False when the question is about the earliest, not the latest.",
    )
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _outcome_is_one_we_record(self) -> SearchPlan:
        allowed = {None, "selected", "runner_up", "not_selected", "unusable"}
        if self.outcome not in allowed:
            raise ValueError(f"outcome must be one of {sorted(x for x in allowed if x)}")
        if self.decided_by not in (None, "agent", "human"):
            raise ValueError("decided_by must be agent or human")
        return self

    def is_empty(self) -> bool:
        """Nothing was asked for in particular.

        Worth knowing, because "show me everything" and "I could not turn your
        question into a search" produce the same object and mean different
        things to the person waiting.
        """
        return not any(
            (
                self.text,
                self.semantic,
                self.scene is not None,
                self.setup is not None,
                self.take is not None,
                self.outcome,
                self.decided_by,
                self.finding,
            )
        )
