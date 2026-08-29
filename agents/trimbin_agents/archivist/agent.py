"""The Archivist: turn a question into a search, and a result into a sentence.

Two calls with a database lookup between them, and the split is the whole
design. The model is good at reading "which takes did we throw out for
continuity in scene 12" and producing filters; it is not the thing that should
decide what the archive contains. So it plans, we search, and then it explains
what came back.

It never sees a row it did not get from the query. An agent that can write the
answer without the evidence will eventually write one that has none — and the
person reads the sentence, not the empty list underneath it.
"""

from __future__ import annotations

import logging

from google import genai
from google.genai import types

from ..common.errors import AgentFailure
from ..config import settings
from ..contracts.base import Strict
from ..contracts.query import Match, Outcome
from ..contracts.search import SearchPlan

log = logging.getLogger(__name__)

PROMPT_VERSION = "archivist/v2"

_PLANNER = """You turn an editor's question into filters over a footage archive.

The archive holds takes. Each take has:
  - a scene, a setup (camera position) and a take number
  - what was decided about it: selected, runner_up, not_selected, unusable
  - who decided: agent (the system) or human (an editor overruling it)
  - the reason, in the words recorded at the time
  - findings, each with a code from a fixed list and a timecode

Choose filters. Do not answer the question and do not invent a scene number the
question did not give you.

`text` searches the words people wrote — reasons, descriptions, slates. Use the
editor's own words, not a paraphrase.

`semantic` describes what the footage looks like, and is compared against the
image itself. Use it only when the question is about the picture rather than
about anything anyone wrote: "the wide ones", "shots with two people".

Leave a field out rather than guessing at it. An empty plan is a valid answer to
"show me everything"."""

_EXPLAINER = """You are describing search results to an editor.

You are given the question and the rows that came back. Say what is there, in
one or two sentences, in the language an editor uses.

Rules that are not negotiable:

Never describe a take that is not in the rows. If the rows are empty, say
nothing was found — do not soften it with something adjacent.

Never restate a count the rows contradict.

If the rows only partly answer the question, say which part. "Three takes in
scene 12 were rejected for continuity; nothing in scene 13 was" is useful.
"Several takes had issues" is not.

Offer a `suggestion` only when nothing was found: a wider constraint worth
trying. Never a consolation result presented as an answer."""


class ArchivistAgent:
    def __init__(self, client: genai.Client | None = None) -> None:
        self._client = client or genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.model_location,
        )

    async def plan(self, question: str) -> SearchPlan:
        """Question in, filters out. No SQL, and no answer."""
        try:
            response = await self._client.aio.models.generate_content(
                model=settings.archivist_model,
                contents=[_PLANNER, f"Question: {question}"],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SearchPlan,
                    # Planning is not a creative act. The same question should
                    # produce the same search, or a result cannot be reproduced.
                    temperature=0.0,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise AgentFailure(f"could not plan the search: {exc}") from exc

        return SearchPlan.model_validate_json(response.text)

    async def explain(
        self,
        question: str,
        matches: list[Match],
        plan: SearchPlan,
    ) -> tuple[str, str]:
        """Say what came back. Returns the answer and, if empty, a suggestion.

        Given the rows and nothing else. The model cannot reach the database
        from here, which is what makes "never describe a take that is not in the
        rows" an arrangement rather than an instruction.
        """
        rendered = _render(matches)

        try:
            response = await self._client.aio.models.generate_content(
                model=settings.archivist_model,
                contents=[
                    _EXPLAINER,
                    f"Question: {question}",
                    f"Filters used: {plan.model_dump_json(exclude_defaults=True)}",
                    f"Rows ({len(matches)}):\n{rendered}",
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_Explanation,
                    temperature=0.1,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise AgentFailure(f"could not describe the results: {exc}") from exc

        explanation = _Explanation.model_validate_json(response.text)
        return explanation.answer, explanation.suggestion


class _Explanation(Strict):
    """Just the two strings.

    A schema this narrow is the point: the model has no field in which to
    return a take, so it cannot return one that was not in the rows.
    """

    answer: str
    suggestion: str = ""


def _render(matches: list[Match]) -> str:
    """The rows, as text the model can read.

    Deliberately terse and complete: every row goes in, none is summarised on
    the way, and nothing is included that did not come from the query.
    """
    if not matches:
        return "(none)"

    lines = []
    for m in matches:
        where = f" at {m.where.start_s:.1f}s" if m.where else ""
        lines.append(
            f"- scene {m.group_id} setup {m.subgroup_id} take {m.take_no}: "
            f"{m.outcome}, {m.reason}{where} (decided by {m.decided_by})"
        )
    return "\n".join(lines)


def outcome_for(matches: list[Match], widened: bool) -> Outcome:
    """What to call the result, from the rows rather than from the model.

    Kept out of the model's hands on purpose. QueryResult refuses to hold
    `found` with no matches, so letting a model name the outcome would turn a
    hallucination into a validation error at best and a wrong answer at worst.
    """
    if not matches:
        return Outcome.NO_MATCH
    return Outcome.WIDENED if widened else Outcome.FOUND


__all__ = ["ArchivistAgent", "PROMPT_VERSION", "outcome_for"]
