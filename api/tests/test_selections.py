"""A human take choice crosses Firestore and ClickHouse without disappearing."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.routes.review import Override, UndoRequest
from app.services import selections


class TestEverySelectionProvesWhatItSaw:
    def test_select_without_a_revision_is_refused(self) -> None:
        from uuid import uuid4

        with pytest.raises(ValidationError):
            Override(clip_id=uuid4(), reason="better performance")

    def test_undo_without_a_revision_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            UndoRequest()


class _Snapshot:
    def __init__(self, data: dict | None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _Ref:
    def __init__(self, data: dict | None = None):
        self.data = data

    async def get(self):
        return _Snapshot(self.data)

    async def set(self, fields: dict, merge: bool = False):
        self.data = {**(self.data or {}), **fields} if merge else dict(fields)


class _Collection:
    def __init__(self, docs: dict[str, _Ref]):
        self.docs = docs

    def document(self, doc_id: str):
        return self.docs.setdefault(doc_id, _Ref())


class _DB:
    def __init__(self, collections: dict[str, dict[str, _Ref]]):
        self.collections = collections

    def collection(self, name: str):
        return _Collection(self.collections.setdefault(name, {}))


class TestArchiveDeliveryIsIdempotent:
    @pytest.mark.asyncio
    async def test_a_retry_does_not_append_the_decision_twice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        event = {
            "event_id": "event-1",
            "project_id": 1,
            "scene": 12,
            "shot": 2,
            "actor": "editor@example.com",
            "rows": [{"clip_id": "00000000-0000-0000-0000-000000000001"}],
            "state": "pending",
        }
        store = _DB(
            {
                selections.COLLECTION: {"event-1": _Ref(event)},
                "shots": {
                    "p1_s12_h2": _Ref(
                        {"selection_event_id": "event-1", "selection_archive_state": "pending"}
                    )
                },
            }
        )
        writes = 0

        async def fake_recorded(project_id: int, event_id: str) -> bool:
            return True

        async def should_not_write(**kwargs):
            nonlocal writes
            writes += 1

        monkeypatch.setattr(selections, "db", lambda: store)
        monkeypatch.setattr(selections.decisions, "already_recorded", fake_recorded)
        monkeypatch.setattr(selections.decisions, "record", should_not_write)

        assert await selections.deliver("event-1") is True
        assert writes == 0
        assert store.collections[selections.COLLECTION]["event-1"].data["state"] == "delivered"
        assert store.collections["shots"]["p1_s12_h2"].data["selection_archive_state"] == (
            "delivered"
        )

    @pytest.mark.asyncio
    async def test_an_unknown_event_is_not_reported_as_delivered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(selections, "db", lambda: _DB({}))
        assert await selections.deliver("missing") is False
