"""Pure evidence safeguards; runtime execution deferred by the owner."""

from uuid import uuid4

import pytest

from app.evidence.contracts import EvidenceError
from app.evidence.projection import eligible
from app.evidence.worker import review_request, windows


def test_windows_cover_final_tail_without_silent_truncation():
    assert windows(65, 30, 2) == [(0, 30), (28, 58), (56, 65)]
    with pytest.raises(EvidenceError, match="overlap"):
        windows(100, 30, 30)
    with pytest.raises(EvidenceError, match="window_limit"):
        windows(1000, 1, 0)


def test_selection_context_keeps_source_and_range():
    source, selection = str(uuid4()), str(uuid4())
    request = review_request(
        {
            "project_id": 1,
            "task": "comparison",
            "sources": [{"id": source, "sha256": "a" * 64, "duration_us": 100}],
            "selections": [
                {
                    "selection_id": selection,
                    "source_id": source,
                    "start_us": 10,
                    "end_us": 80,
                    "text": "Editor-approved context",
                }
            ],
            "brief": "Compare performance",
            "command_id": str(uuid4()),
            "evidence_revision": 4,
        }
    )
    assert request.candidates[0].id == selection
    assert request.evidence[0].start_us == 10
    assert request.evidence[0].end_us == 80


def test_retracted_and_historical_rows_excluded_from_current_search():
    rows = [
        {"id": "a", "current": True, "decision": "accepted"},
        {"id": "b", "current": False, "decision": "accepted"},
        {"id": "c", "current": True, "decision": "retracted"},
    ]
    assert eligible({"items": rows}) == [rows[0]]
