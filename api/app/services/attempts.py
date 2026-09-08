"""Non-destructive, revisioned performance boundaries and review choices."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from google.cloud import firestore
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import analysis_store, revisions
from .jobs import db


class AttemptItem(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: UUID
    proposal_id: UUID | None = None
    label: str = Field(min_length=1, max_length=100)
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    state: Literal[
        "proposed", "reviewed", "clean", "shortlisted", "director_choice", "rejected"
    ] = "proposed"
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def positive_range(self):
        if self.end_s <= self.start_s:
            raise ValueError("An attempt must end after it starts.")
        return self


class AttemptProposal(BaseModel):
    attempt_id: UUID
    run_id: UUID
    start_s: float
    end_s: float
    action: str
    observation: str
    interpretation: str
    recommendation: str
    confidence: float
    intent: str
    starts_before_window: bool
    ends_after_window: bool
    evidence_segment_ids: list[UUID]
    model_id: str
    prompt_version: str


class AttemptSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rev: int = Field(ge=0)
    command_id: UUID
    items: list[AttemptItem] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({row.id for row in self.items}) != len(self.items):
            raise ValueError("Attempt IDs must be unique within a recording.")
        return self


class AttemptState(BaseModel):
    project_id: int
    clip_id: UUID
    rev: int = 0
    duration_s: float
    items: list[AttemptItem]
    proposals: list[AttemptProposal]
    analysis_changed: bool = False
    updated_at: datetime | None = None
    analysis_state: str = ""
    analysis_error: str = ""


class AttemptHistoryEntry(BaseModel):
    rev: int
    updated_at: datetime
    count: int


class AttemptHistory(BaseModel):
    versions: list[AttemptHistoryEntry]


def reference(project_id: int, clip_id: UUID):
    return db().collection("performance_boundaries").document(f"{project_id}_{clip_id}")


async def context(project_id: int, clip_id: UUID) -> tuple[float, list[dict]]:
    # Read original identity rather than requiring accepted placement: staging
    # footage can have reviewable performances before its shot is resolved.
    result, proposals = await asyncio.gather(
        analysis_store.clip_identity(project_id, clip_id),
        analysis_store.read_attempts(project_id, clip_id),
    )
    if not result:
        raise HTTPException(404, "No active source recording in this project.")
    return float(result["duration_s"]), proposals


def materialize(
    project_id: int, clip_id: UUID, duration: float, proposals: list[dict], document: dict
) -> AttemptState:
    default_items = [
        AttemptItem(
            id=row["attempt_id"],
            proposal_id=row["attempt_id"],
            label=f"Attempt {i + 1}",
            start_s=row["start_s"],
            end_s=row["end_s"],
        )
        for i, row in enumerate(proposals)
    ]
    proposal_ids = sorted(str(row["attempt_id"]) for row in proposals)
    return AttemptState(
        project_id=project_id,
        clip_id=clip_id,
        duration_s=duration,
        rev=int(document.get("rev", 0)),
        items=document.get("items", default_items),
        proposals=proposals,
        analysis_changed=bool(document and document.get("proposal_ids", []) != proposal_ids),
        updated_at=document.get("updated_at"),
    )


async def read(project_id: int, clip_id: UUID, revision: int | None = None) -> AttemptState:
    ref = reference(project_id, clip_id)
    if revision is not None:
        ref = ref.collection("versions").document(str(revision))
    (duration, proposals), snapshot = await asyncio.gather(context(project_id, clip_id), ref.get())
    if revision is not None and not snapshot.exists:
        raise HTTPException(404, "No such boundary revision.")
    return materialize(project_id, clip_id, duration, proposals, snapshot.to_dict() or {})


async def history(project_id: int, clip_id: UUID) -> AttemptHistory:
    rows = []
    async for snap in (
        reference(project_id, clip_id)
        .collection("versions")
        .order_by("rev", direction=firestore.Query.DESCENDING)
        .limit(30)
        .stream()
    ):
        row = snap.to_dict() or {}
        rows.append(
            AttemptHistoryEntry(
                rev=row["rev"], updated_at=row["updated_at"], count=len(row["items"])
            )
        )
    return AttemptHistory(versions=rows)


async def save(project_id: int, clip_id: UUID, body: AttemptSave, actor: str) -> AttemptState:
    duration, proposals = await context(project_id, clip_id)
    if any(row.end_s > duration + 0.001 for row in body.items):
        raise HTTPException(422, "A boundary extends beyond the source recording.")
    ref = reference(project_id, clip_id)
    receipt = ref.collection("commands").document(str(body.command_id))
    items = [row.model_dump(mode="json") for row in body.items]
    request = {"actor": actor, "rev": body.rev, "items": items}
    proposal_ids = list({row.proposal_id for row in body.items if row.proposal_id})
    historical_ids: set[str] = set()
    if proposal_ids:
        found = await (await analysis_store.client()).query(
            """SELECT DISTINCT attempt_id FROM performance_attempts
            WHERE project_id={p:UInt32} AND clip_id={c:UUID} AND attempt_id IN {ids:Array(UUID)}""",
            parameters={"p": project_id, "c": clip_id, "ids": proposal_ids},
        )
        historical_ids = {str(row[0]) for row in found.result_rows}

    @firestore.async_transactional
    async def commit(transaction):
        snapshot = await ref.get(transaction=transaction)
        replay = await receipt.get(transaction=transaction)
        prior = snapshot.to_dict() or {}
        if replay.exists:
            remembered = replay.to_dict() or {}
            if remembered.get("request") != request:
                raise HTTPException(409, "This command key belongs to a different boundary edit.")
            return remembered["result"]
        revisions.check(body.rev, int(prior.get("rev", 0)))
        known_proposals = (
            historical_ids
            | {str(p["attempt_id"]) for p in proposals}
            | {row.get("proposal_id") for row in prior.get("items", []) if row.get("proposal_id")}
        )
        if any(
            row.get("proposal_id") and row["proposal_id"] not in known_proposals for row in items
        ):
            raise HTTPException(
                422,
                "A proposal reference is not part of this recording's current or saved evidence.",
            )
        # The initial machine view is recoverable even after the first manual edit.
        if not prior:
            baseline = materialize(project_id, clip_id, duration, proposals, {})
            transaction.set(
                ref.collection("versions").document("0"),
                {
                    "rev": 0,
                    "items": [r.model_dump(mode="json") for r in baseline.items],
                    "updated_at": datetime.now(UTC),
                },
            )
        document = {
            "project_id": project_id,
            "clip_id": str(clip_id),
            "rev": body.rev + 1,
            "items": items,
            "updated_by": actor,
            "updated_at": datetime.now(UTC),
            "proposal_ids": sorted(str(row["attempt_id"]) for row in proposals),
        }
        transaction.set(ref, document)
        transaction.set(ref.collection("versions").document(str(body.rev + 1)), document)
        transaction.set(receipt, {"request": request, "result": document})
        return document

    document = await commit(db().transaction())
    return materialize(project_id, clip_id, duration, proposals, document)


async def validate_reference(
    project_id: int, clip_id: UUID, attempt_id: UUID | None, revision: int
) -> None:
    """Selection provenance can point to a historical boundary, not another source."""
    if attempt_id is None:
        if revision:
            raise HTTPException(422, "An attempt revision requires an attempt ID.")
        return
    if revision > 0:
        snapshot = (
            await reference(project_id, clip_id)
            .collection("versions")
            .document(str(revision))
            .get()
        )
        if snapshot.exists and any(
            str(row["id"]) == str(attempt_id) for row in (snapshot.to_dict() or {}).get("items", [])
        ):
            return
    else:
        found = await (await analysis_store.client()).query(
            """SELECT count() FROM performance_attempts
            WHERE project_id={p:UInt32} AND clip_id={c:UUID} AND attempt_id={a:UUID}""",
            parameters={"p": project_id, "c": clip_id, "a": attempt_id},
        )
        if found.result_rows and found.result_rows[0][0]:
            return
    raise HTTPException(422, "The attempt reference does not belong to this source/revision.")
