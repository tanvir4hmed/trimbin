"""Command invariants with a deterministic transactional store double.

These test transaction bodies, not Firestore's concurrency implementation.
"""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import jobs


class Store:
    def __init__(self):
        self.data = {}

    def collection(self, name):
        return Reference(self, name)

    def transaction(self):
        return self

    def set(self, ref, payload):
        self.data[ref.path] = deepcopy(payload)

    def update(self, ref, payload):
        data = self.data.setdefault(ref.path, {})
        for key, value in payload.items():
            if isinstance(value, jobs.documents.ArrayUnion):
                data[key] = data.get(key, []) + list(value.values)
            else:
                data[key] = deepcopy(value)


class Reference:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def document(self, name):
        return Reference(self.store, f"{self.path}/{name}")

    collection = document

    async def get(self, **kwargs):
        data = deepcopy(self.store.data.get(self.path))
        return SimpleNamespace(exists=data is not None, to_dict=lambda: data)


@pytest.fixture
def store(monkeypatch):
    memory = Store()
    monkeypatch.setattr(jobs, "db", lambda: memory)
    monkeypatch.setattr(jobs.documents, "async_transactional", lambda fn: fn)
    return memory


@pytest.mark.asyncio
async def test_progress_retry_is_counted_once_and_success_never_downgraded(store):
    job_id, clip_id = uuid4(), uuid4()
    key = f"{jobs.COLLECTION}/{job_id}"
    store.data[key] = {"total_items": 1, "completed_items": 0, "failed_items": 0}
    await jobs.record_progress(job_id, clip_id, False, "temporary failure")
    await jobs.record_progress(job_id, clip_id, False, "temporary failure")
    assert store.data[key]["failed_items"] == 1
    await jobs.record_progress(job_id, clip_id, True)
    await jobs.record_progress(job_id, clip_id, True)
    await jobs.record_progress(job_id, clip_id, False, "late failed delivery")
    assert store.data[key]["completed_items"] == 1
    assert store.data[key]["failed_items"] == 0
    assert store.data[key]["failures"] == []


@pytest.mark.asyncio
async def test_first_auto_filed_item_does_not_finish_entire_batch(store):
    job_id, clip_id = uuid4(), uuid4()
    key = f"{jobs.COLLECTION}/{job_id}"
    store.data[key] = {
        "total_items": 8,
        "state": jobs.State.PROCESSING,
        "items": [{"clip_id": str(clip_id), "verified": False}],
    }
    await jobs.mark_verified(job_id, {str(clip_id)})
    assert store.data[key]["items"][0]["verified"]
    assert store.data[key]["state"] == jobs.State.PROCESSING
