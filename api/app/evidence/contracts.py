from typing import Literal
from uuid import UUID

from pydantic import Field

from ..inference.contracts import Contract, Span


class EvidenceError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Note(Span):
    kind: Literal["observation", "moment", "attempt", "slate", "continuity", "speech"]
    text: str = Field(min_length=1, max_length=4000)


class EditCommand(Contract):
    command_id: UUID
    expected_revision: int = Field(ge=0)
    operation: Literal["note", "correct", "select", "unselect", "place"]
    item_id: UUID | None = None
    note: Note | None = None
    decision: Literal["accepted", "uncertain", "retracted"] = "accepted"
    source_id: UUID | None = None
    scene: str = Field(default="", max_length=120)
    shot: str = Field(default="", max_length=120)
    take: str = Field(default="", max_length=120)


class AnalyzeCommand(Contract):
    command_id: UUID
    expected_revision: int = Field(ge=0)
    source_id: UUID
    task: Literal["visual", "slate"] = "visual"
    mode: Literal["fixture", "nebius"]
    window_seconds: int = Field(default=30, ge=1, le=120)
    overlap_seconds: int = Field(default=2, ge=0, le=10)
    sample_every_seconds: int = Field(default=2, ge=1, le=30)
    allowed_labels: dict[str, list[str]] = Field(default_factory=dict)


class CompareCommand(Contract):
    command_id: UUID
    expected_revision: int = Field(ge=0)
    task: Literal["comparison", "continuity"] = "comparison"
    mode: Literal["fixture", "nebius"]
    brief: str = Field(min_length=1, max_length=16000)


class Search(Contract):
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["text", "semantic"] = "text"
    source_id: UUID | None = None
    kind: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=20, ge=1, le=100)
