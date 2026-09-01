"""The independent window observer's contract and product boundary."""

from trimbin_agents.contracts.base import FindingCode
from trimbin_agents.contracts.segments import SegmentObservation
from trimbin_agents.segment.agent import PROMPT, SegmentModelResponse


def test_finding_codes_stringify_to_the_archive_value() -> None:
    assert str(FindingCode.CONTINUITY_BLOCKING) == "continuity.blocking"


def test_segment_contract_is_searchable_without_a_finding() -> None:
    segment = SegmentObservation(description="A hand places a red cup on the table.")
    assert segment.description.startswith("A hand")
    assert segment.findings == []


def test_vertex_wire_schema_stays_constraint_light() -> None:
    schema = SegmentModelResponse.model_json_schema()
    for field in schema["properties"].values():
        assert "maxItems" not in field
        assert "default" not in field
    assert set(schema["required"]) == {
        "description",
        "transcript",
        "actions",
        "objects",
        "speakers",
        "shot_size",
        "camera_motion",
        "findings",
    }


def test_the_observer_is_forbidden_from_ranking_performance() -> None:
    lowered = PROMPT.lower()
    assert "do not choose a take" in lowered
    assert "do not judge acting" in lowered
    assert "human editor" in lowered
