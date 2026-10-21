"""Grounded inference contracts. Microseconds are analysis coordinates, not NLE frames."""

from __future__ import annotations

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Task = Literal["slate", "visual", "continuity", "comparison", "draft", "speech"]
SHA256 = r"^[a-f0-9]{64}$"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class Source(Contract):
    id: UUID
    sha256: str = Field(pattern=SHA256)
    duration_us: int = Field(gt=0, strict=True)


class Span(Contract):
    source_id: UUID
    start_us: int = Field(ge=0, strict=True)
    end_us: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def ordered(self) -> Span:
        if self.end_us <= self.start_us:
            raise ValueError("Empty or reversed source interval")
        return self


class Window(Span):
    id: str = Field(min_length=1, max_length=120)


class Evidence(Window):
    text: str = Field(min_length=1, max_length=16000)
    modality: Literal["visual", "audio", "editor"]


class Frame(Contract):
    id: str = Field(min_length=1, max_length=120)
    source_id: UUID
    at_us: int = Field(ge=0, strict=True)
    sha256: str = Field(pattern=SHA256)
    mime: Literal["image/png", "image/jpeg"]


class TaskRequest(Contract):
    schema_version: Literal["inference-request-v1"] = "inference-request-v1"
    timestamp_origin: Literal["video_start"] = "video_start"
    project_id: int = Field(gt=0, strict=True)
    task: Task
    sources: list[Source] = Field(min_length=1, max_length=64)
    windows: list[Window] = Field(min_length=1, max_length=256)
    frames: list[Frame] = Field(default_factory=list, max_length=256)
    evidence: list[Evidence] = Field(default_factory=list, max_length=1000)
    candidates: list[Window] = Field(default_factory=list, max_length=256)
    brief: str = Field(default="", max_length=32000)
    brief_revision: str = Field(min_length=1, max_length=120)
    evidence_revision: str = Field(min_length=1, max_length=120)
    recipe: str = Field(min_length=1, max_length=4000)
    allowed_labels: dict[str, list[str]] = Field(default_factory=dict)

    def contains(self, span: Span) -> bool:
        return any(
            w.source_id == span.source_id and w.start_us <= span.start_us < span.end_us <= w.end_us
            for w in self.windows
        )

    @model_validator(mode="after")
    def grounded(self) -> TaskRequest:
        source_map = {s.id: s for s in self.sources}
        if len(source_map) != len(self.sources):
            raise ValueError("Duplicate source ID")
        for items in (self.windows, self.frames, self.evidence, self.candidates):
            if len({item.id for item in items}) != len(items):
                raise ValueError("Duplicate input ID")
        if {f.id for f in self.frames} & {e.id for e in self.evidence}:
            raise ValueError("Citation IDs must be unambiguous")
        for window in self.windows:
            source = source_map.get(window.source_id)
            if source is None or window.end_us > source.duration_us:
                raise ValueError("Window outside source")
        for span in [*self.evidence, *self.candidates]:
            if not self.contains(span):
                raise ValueError("Input outside allowed windows")
        for frame in self.frames:
            if not any(
                w.source_id == frame.source_id and w.start_us <= frame.at_us < w.end_us
                for w in self.windows
            ):
                raise ValueError("Frame outside allowed windows")
        if self.task in {"slate", "visual"} and not self.frames:
            raise ValueError("Visual tasks require actual frames")
        if self.task in {"comparison", "draft"} and not self.candidates:
            raise ValueError("Editorial tasks require allowed candidates")
        if self.task in {"continuity", "comparison", "draft"} and not (
            self.frames or self.evidence
        ):
            raise ValueError("Reasoning requires source evidence")
        if set(self.allowed_labels) - {"scene", "shot", "take"}:
            raise ValueError("Unknown slate label category")
        return self


class Finding(Span):
    kind: Literal["slate", "observation", "continuity", "speech"]
    text: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    citations: list[str] = Field(min_length=1, max_length=64)
    labels: dict[str, str] = Field(default_factory=dict)


class Choice(Contract):
    candidate_id: str
    reason: str = Field(min_length=1, max_length=4000)
    citations: list[str] = Field(min_length=1, max_length=64)


class TaskOutput(Contract):
    status: Literal["ok", "abstained"]
    reason: str = Field(max_length=4000)
    findings: list[Finding] = Field(default_factory=list, max_length=1000)
    ranking: list[Choice] = Field(default_factory=list, max_length=256)
    draft: list[Choice] = Field(default_factory=list, max_length=256)

    def validate_for(self, request: TaskRequest) -> None:
        citations = {item.id: item for item in [*request.frames, *request.evidence]}
        candidates = {item.id: item for item in request.candidates}
        if self.status == "abstained":
            if not self.reason or self.findings or self.ranking or self.draft:
                raise ValueError("Abstention must have a reason and no asserted findings")
            return
        expected = {
            "slate": "slate",
            "visual": "observation",
            "continuity": "continuity",
            "speech": "speech",
        }
        if request.task != "comparison" and self.ranking:
            raise ValueError("Unexpected ranking")
        if request.task != "draft" and self.draft:
            raise ValueError("Unexpected draft")
        if request.task in {"comparison", "draft"} and self.findings:
            raise ValueError("Editorial choices must reference supplied evidence")
        if not (self.findings or self.ranking or self.draft):
            raise ValueError("Empty success must be an explicit abstention")
        for finding in self.findings:
            if finding.kind != expected.get(request.task) or not request.contains(finding):
                raise ValueError("Invalid finding kind or source interval")
            for citation in finding.citations:
                item = citations.get(citation)
                if item is None:
                    raise ValueError("Unknown citation")
                if item.source_id == finding.source_id:
                    overlaps = (
                        finding.start_us <= item.at_us < finding.end_us
                        if isinstance(item, Frame)
                        else item.start_us < finding.end_us and item.end_us > finding.start_us
                    )
                    if not overlaps:
                        raise ValueError("Citation does not overlap finding")
                elif request.task != "continuity":
                    raise ValueError("Citation belongs to another source")
            if not any(citations[c].source_id == finding.source_id for c in finding.citations):
                raise ValueError("Finding lacks evidence from its source")
            if finding.kind != "slate" and finding.labels:
                raise ValueError("Labels only belong to slate findings")
            for category, label in finding.labels.items():
                if label not in request.allowed_labels.get(category, []):
                    raise ValueError("Unpermitted slate label")
        if len({c.candidate_id for c in self.ranking}) != len(self.ranking):
            raise ValueError("Repeated ranked candidate")
        for choice in [*self.ranking, *self.draft]:
            candidate = candidates.get(choice.candidate_id)
            if candidate is None or any(c not in citations for c in choice.citations):
                raise ValueError("Unknown candidate or citation")

            def overlaps_candidate(citation: str, target: Window = candidate) -> bool:
                item = citations[citation]
                if item.source_id != target.source_id:
                    return False
                if isinstance(item, Frame):
                    return target.start_us <= item.at_us < target.end_us
                return item.start_us < target.end_us and item.end_us > target.start_us

            if not any(overlaps_candidate(c) for c in choice.citations):
                raise ValueError("Choice lacks source evidence")


class ModelProfile(Contract):
    model_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    precision: str = Field(min_length=1)
    modalities: list[Literal["text", "image", "embedding"]] = Field(min_length=1)
    response_format: Literal["json_object", "json_schema"] = "json_object"
    max_input_bytes: int = Field(gt=0, le=128 * 1024**2)
    max_frames: int = Field(ge=0, le=256)
    license_url: str = ""
    deployment_generation: str = Field(min_length=1)


class EmbeddingIdentity(Contract):
    provider: Literal["nebius-token-factory"] = "nebius-token-factory"
    model_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    precision: str = Field(min_length=1)
    deployment_generation: str = Field(min_length=1)
    dimension: int = Field(gt=0, le=65536)
    normalization: Literal["none", "l2"]
    preprocessing_version: str = Field(min_length=1)
    index_generation: str = Field(min_length=1)

    def require_compatible(self, other: EmbeddingIdentity) -> None:
        if self != other:
            raise ValueError("Incompatible corpus/query embedding generation")
