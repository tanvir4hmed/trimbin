"""Rights-aware editorial evidence manifests; no training or media export."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from trimbin_agents.contracts.segments import SegmentObservation

from . import analysis_store, attempts, finding_actions
from .jobs import db


class DatasetWindow(BaseModel):
    segment_id: UUID
    run_id: UUID
    start_s: float
    end_s: float
    model_id: str
    prompt_version: str
    observation: SegmentObservation | None = None
    observation_time_unit: Literal["seconds_relative_to_window_start"] = (
        "seconds_relative_to_window_start"
    )


class DatasetMedia(BaseModel):
    clip_id: UUID
    content_hash: str = ""
    duration_s: float
    measured_fps: float
    time_unit: Literal["source_seconds"] = "source_seconds"


class DatasetFinding(BaseModel):
    event_id: UUID
    finding_id: UUID
    run_id: UUID
    revision: int
    action: str
    code: str
    detail: str
    severity: str
    start_s: float
    end_s: float
    evidence_segment_ids: list[UUID]
    sources: list[str]
    actor_role: str
    occurred_at: datetime
    retracts_event_id: UUID | None = None
    restored_action: str = ""


class DatasetOccurrence(BaseModel):
    id: str
    start_s: float
    end_s: float
    position: int
    note: str = ""
    attempt_id: UUID | None = None
    attempt_revision: int = 0


class EditorialDatasetRecord(BaseModel):
    schema_version: Literal["editorial-evidence/1"] = "editorial-evidence/1"
    project_id: int
    exported_at: datetime
    media: DatasetMedia
    training_eligible: Literal[False] = False
    rights_status: Literal["unverified"] = "unverified"
    usage_note: str = (
        "Operational review export only. Obtain explicit footage, participant and training "
        "permissions before dataset release or training."
    )
    attempt_state: attempts.AttemptState
    windows: list[DatasetWindow]
    finding_events: list[DatasetFinding]
    film_revision: int
    film_occurrences: list[DatasetOccurrence]
    scope: list[str] = Field(
        default_factory=lambda: [
            "Current attempt boundary revision and current-run machine proposals",
            "Available finding history; includes review retractions",
            "Up to 1000 latest unique analysis-window payloads; older runs may be incomplete",
            "Current saved film occurrences, not every historical edit",
        ]
    )
    missing_labels: list[str] = Field(
        default_factory=lambda: [
            "Training consent and license eligibility",
            "Comparison exposure/order and all candidates shown to each reviewer",
            "Independent expert adjudication and inter-reviewer agreement",
            "Rational source timebase and professional conform mapping",
        ]
    )


async def export_clip(project_id: int, clip_id: UUID) -> EditorialDatasetRecord:
    state, archive, operational, sequence, media, windows = await asyncio.gather(
        attempts.read(project_id, clip_id),
        analysis_store.read(project_id, clip_id),
        finding_actions.states_for_clip(project_id, clip_id),
        db().collection("film_sequences").document(str(project_id)).get(),
        (await analysis_store.client()).query(
            """SELECT content_hash, fps FROM clips
            WHERE project_id={p:UInt32} AND clip_id={c:UUID} AND status='active'
            ORDER BY ingested_at DESC LIMIT 1""",
            parameters={"p": project_id, "c": clip_id},
        ),
        (await analysis_store.client()).query(
            """SELECT segment_id, run_id, start_s, end_s, model_id, prompt_version,
                      observation_json FROM clip_segments
            WHERE project_id={p:UInt32} AND clip_id={c:UUID}
            ORDER BY occurred_at DESC LIMIT 1 BY segment_id LIMIT 1000""",
            parameters={"p": project_id, "c": clip_id},
        ),
    )
    events = finding_actions.overlay(archive, operational)["history"]
    document = sequence.to_dict() or {}
    fingerprint, fps = media.result_rows[0] if media.result_rows else ("", 0)
    return EditorialDatasetRecord(
        project_id=project_id,
        exported_at=datetime.now(UTC),
        media=DatasetMedia(
            clip_id=clip_id,
            content_hash=str(fingerprint),
            duration_s=state.duration_s,
            measured_fps=float(fps),
        ),
        attempt_state=state,
        windows=[
            DatasetWindow(
                segment_id=row[0],
                run_id=row[1],
                start_s=row[2],
                end_s=row[3],
                model_id=row[4],
                prompt_version=row[5],
                observation=SegmentObservation.model_validate_json(row[6])
                if row[6] and row[6] != "{}"
                else None,
            )
            for row in windows.result_rows
        ],
        finding_events=[DatasetFinding.model_validate(row) for row in events],
        film_revision=int(document.get("rev", 0)),
        film_occurrences=[
            DatasetOccurrence(
                id=str(row["id"]),
                start_s=row["start_s"],
                end_s=row["end_s"],
                position=i,
                note=row.get("note", ""),
                attempt_id=row.get("attempt_id"),
                attempt_revision=int(row.get("attempt_revision", 0)),
            )
            for i, row in enumerate(document.get("ranges", []))
            if str(row["clip_id"]) == str(clip_id)
        ],
    )
