"""Asking the archive a question in plain language.

The shape here is: the model plans, the database answers, the model describes
what came back. It never writes the query and never sees a row the query did not
return, so an answer with nothing behind it is not a thing it can produce — the
schema it replies with has no field to put a take in.

Open to anyone on a public project, for the same reason the accuracy page is: a
system whose whole claim is that it remembers why should let people ask.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ..auth import Principal, current_principal
from ..config import settings
from ..services import search

log = logging.getLogger(__name__)
router = APIRouter(prefix="/ask", tags=["ask"])


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=500)

    @field_validator("question")
    @classmethod
    def _tidy(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Ask something.")
        return cleaned


@router.get("/{project_id}/suggestions")
async def suggestions(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """Questions worth asking, so an empty search box is not a blank page.

    Written rather than generated. A model asked to invent example questions
    produces ones the archive cannot answer, and a suggestion that returns
    nothing is worse than no suggestion — it reads as the system being empty.
    """
    await principal.assert_can_read(project_id)

    return {
        "project_id": project_id,
        "suggestions": [
            "Which takes were rejected for continuity?",
            "What did an editor overrule?",
            "Show me everything that was recommended",
            "Which takes have a framing problem?",
            "What was rejected in scene 1?",
        ],
    }


@router.post("/{project_id}")
async def ask(
    project_id: int,
    body: Question,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """A question in, takes with their reasons out."""
    await principal.assert_can_read(project_id)

    from trimbin_agents.archivist.agent import (
        PROMPT_VERSION,
        ArchivistAgent,
        outcome_for,
    )
    from trimbin_agents.common.errors import AgentFailure

    agent = ArchivistAgent()

    try:
        plan = await agent.plan(body.question)
    except AgentFailure as exc:
        log.warning("could not plan a search for %r: %s", body.question, exc)
        # Said plainly. A failed search dressed as an empty one tells the person
        # their archive has nothing in it, which is a different and wrong thing.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Could not turn that into a search. Try asking it another way.",
        ) from exc

    filters = plan.model_dump()
    embedding = None
    if plan.semantic:
        embedding = await _embed(plan.semantic)

    try:
        rows, sql, elapsed_ms = await search.run(project_id, filters, embedding)
    except search.SearchUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    widened = False
    if not rows and not plan.is_empty():
        # Offered, not substituted. The near misses are labelled as near misses,
        # because a person asked about scene 12 would act on rows from scene 9
        # without noticing they were not what they asked for.
        try:
            rows, sql, elapsed_ms = await search.widen(project_id, filters)
        except search.SearchUnavailable as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
        widened = bool(rows)

    matches = [_as_match(r) for r in rows]

    try:
        answer, suggestion = await agent.explain(body.question, matches, plan)
    except AgentFailure:
        # The rows are the answer; the sentence is a convenience. Losing the
        # sentence should not lose the result.
        log.warning("could not describe %d rows; returning them plainly", len(matches))
        answer = (
            f"{len(matches)} take{'s' if len(matches) != 1 else ''} matched."
            if matches
            else "Nothing matched."
        )
        suggestion = ""

    return {
        "question": body.question,
        "outcome": outcome_for(matches, widened).value,
        "answer": answer,
        "suggestion": suggestion if not matches else "",
        "matches": [m.model_dump(mode="json") for m in matches],
        # Shown so the result can be checked rather than trusted.
        "sql": sql,
        "filters": plan.model_dump(exclude_defaults=True),
        "elapsed_ms": elapsed_ms,
        "prompt_version": PROMPT_VERSION,
    }


async def _embed(description: str) -> list[float] | None:
    """A vector for a description of what the footage looks like.

    Returns None on failure rather than raising: the structured and text filters
    still work without it, and a search that narrows less is better than one
    that does not run.
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.model_location,
        )
        response = await client.aio.models.embed_content(
            model=settings.embedding_model,
            contents=[description],
            config=types.EmbedContentConfig(output_dimensionality=768),
        )
        return list(response.embeddings[0].values)
    except Exception:
        log.exception("could not embed %r; searching without it", description)
        return None


def _as_match(row: dict):
    """One row, as the contract the interface reads.

    The first finding's timecode becomes `where`, so a result is something the
    player can seek to rather than a sentence about a problem somewhere.
    """
    from trimbin_agents.contracts.base import TimeRange
    from trimbin_agents.contracts.query import Match

    starts = row.get("finding_starts_s") or []
    codes = row.get("finding_codes") or []
    where = None
    if starts:
        start = float(starts[0])
        end = float(row.get("usable_to_s") or start + 2.0)
        where = TimeRange(start_s=start, end_s=max(start + 0.05, end))

    return Match(
        clip_id=row["clip_id"],
        group_id=int(row["scene"]),
        subgroup_id=int(row["setup"]),
        take_no=int(row.get("take_no") or 0),
        duration_s=float(row.get("duration_s") or 0.0),
        description=(
            str(row.get("reason") or "")[:300]
            if row.get("reason_code") in {"segment.match", "finding.match"}
            else ", ".join(str(c) for c in codes[:3]) or "no findings"
        ),
        outcome=str(row["outcome"]),
        reason=str(row["reason"])[:200],
        decided_by=str(row["decided_by"]),
        playlist_uri=str(row.get("proxy_uri") or ""),
        where=where,
        relevance=min(1.0, max(0.0, float(row.get("relevance") or 0.0))),
    )
