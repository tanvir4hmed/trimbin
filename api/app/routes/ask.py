"""Asking the archive a question in plain language.

The shape here is: the model plans, the database answers, the model describes
what came back. It never writes the query and never sees a row the query did not
return, so an answer with nothing behind it is not a thing it can produce — the
schema it replies with has no field to put a take in.

Open to anyone on a public project, for the same reason the accuracy page is: a
system whose whole claim is that it remembers why should let people ask.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ..auth import Principal, current_principal
from ..config import settings
from ..services import search, structure

log = logging.getLogger(__name__)

# How far before a moment playback starts. Long enough to see it coming, short
# enough not to land in the previous beat.
PLAYBACK_PREROLL_S = 1.5
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
        if embedding is None:
            # A semantic request without a vector does not degrade to a useful
            # text search: the whole natural-language phrase becomes a literal
            # gate and a transient model fault is reported as "no match". Say
            # the search is unavailable so nobody acts on a false empty result.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Semantic search is temporarily unavailable. Try again.",
            )

    widened = False
    try:
        # Segment, finding and moment retrieval share one request-scoped
        # official MCP session. Starting a new subprocess per query made a
        # correct search feel broken without buying any additional isolation.
        async with search.execution_session():
            rows, sql, elapsed_ms = await search.run(project_id, filters, embedding)
            if not rows and not plan.is_empty():
                # Offered, not substituted. The near misses are labelled as near
                # misses, because a person asked about scene 12 would act on rows
                # from scene 9 without noticing they were not what they asked for.
                rows, sql, elapsed_ms = await search.widen(project_id, filters)
                widened = bool(rows)
    except search.SearchUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    matches = [_as_match(r) for r in rows]
    scenes = await structure.for_project(project_id)
    rendered_matches = _with_display_codes(matches, scenes)

    # The evidence rows already contain the exact description and time range.
    # A second model call merely paraphrased them and added 10-20 seconds after
    # the result existed. Keep the model where it adds value — planning the
    # hybrid retrieval — and render its verified result deterministically.
    answer, suggestion = _result_copy(rendered_matches, widened)

    return {
        "question": body.question,
        "outcome": outcome_for(matches, widened).value,
        "answer": answer,
        "suggestion": suggestion if not matches else "",
        "matches": rendered_matches,
        # Shown so the result can be checked rather than trusted.
        "sql": sql,
        "filters": plan.model_dump(exclude_defaults=True),
        "elapsed_ms": elapsed_ms,
        "prompt_version": PROMPT_VERSION,
    }


async def _embed(description: str) -> list[float] | None:
    """A vector for a description of what the footage looks like.

    Returns None after one retry. The caller may still run a purely structured
    query, but must not turn a failed semantic search into a false empty result.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=settings.project_id,
        location=settings.model_location,
    )
    for attempt in range(2):
        try:
            response = await client.aio.models.embed_content(
                model=settings.embedding_model,
                contents=[description],
                config=types.EmbedContentConfig(output_dimensionality=768),
            )
            return list(response.embeddings[0].values)
        except Exception:
            if attempt == 0:
                await asyncio.sleep(0.25)
                continue
            log.exception("could not embed %r after retry; searching without it", description)
    return None


def _with_display_codes(matches: list, scenes: list[structure.Scene]) -> list[dict]:
    """Add production-facing codes without changing internal navigation ids."""
    scene_codes = {item.scene: item.scene_code or str(item.scene) for item in scenes}
    shot_codes = {
        (item.scene, shot.shot): shot.slug or str(shot.shot)
        for item in scenes
        for shot in item.shots
    }
    rendered: list[dict] = []
    for match in matches:
        row = match.model_dump(mode="json")
        row["scene_code"] = scene_codes.get(match.group_id, str(match.group_id))
        row["shot_code"] = shot_codes.get(
            (match.group_id, match.subgroup_id), str(match.subgroup_id)
        )
        rendered.append(row)
    return rendered


def _result_copy(matches: list[dict], widened: bool) -> tuple[str, str]:
    if not matches:
        return (
            "Nothing matched that request in this project.",
            "Try a scene, shot, take, spoken line, visible action, object, or issue.",
        )

    first = matches[0]
    where = first.get("where")
    at = f" at {float(where['start_s']):.1f}s" if where else ""
    scope = "Closest match" if widened else "Best match"
    count = f"{len(matches)} playable moment{'s' if len(matches) != 1 else ''}"
    answer = (
        f"Found {count}. {scope}: Scene {first['scene_code']}, Shot "
        f"{first['shot_code']}, Take {first['take_no']}{at} — {first['reason']}"
    )
    return answer, ""


def _clipped(text: str, limit: int) -> str:
    """Cut at a word, and say that it was cut.

    A hard slice ended answers like "…his friends do not like h", which reads as
    a rendering fault rather than a shortened sentence. When a match comes from
    a segment the reason is that segment's description, and descriptions are
    long enough that this was the common case, not the rare one.
    """
    if len(text) <= limit:
        return text
    head = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return f"{head or text[:limit]}…"


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
    play_from = 0.0
    if starts:
        start = float(starts[0])
        end = float(row.get("usable_to_s") or start + 2.0)
        where = TimeRange(start_s=start, end_s=max(start + 0.05, end))
        # A run-up, not a wider claim. `where` keeps the true span; playback
        # begins a beat earlier so the moment is not already over by the time
        # somebody has registered what they are looking at.
        play_from = max(0.0, start - PLAYBACK_PREROLL_S)

    return Match(
        clip_id=row["clip_id"],
        group_id=int(row["scene"]),
        subgroup_id=int(row["setup"]),
        take_no=int(row.get("take_no") or 0),
        duration_s=float(row.get("duration_s") or 0.0),
        description=(
            _clipped(str(row.get("reason") or ""), 300)
            if row.get("reason_code") in {"segment.match", "finding.match"}
            else ", ".join(str(c) for c in codes[:3]) or "no findings"
        ),
        outcome=str(row["outcome"]),
        reason=_clipped(str(row["reason"]), 200),
        decided_by=str(row["decided_by"]),
        playlist_uri=str(row.get("proxy_uri") or ""),
        where=where,
        play_from_s=play_from,
        relevance=min(1.0, max(0.0, float(row.get("relevance") or 0.0))),
    )
