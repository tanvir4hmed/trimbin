"""Real PostgreSQL cutover tests: transaction replay, increments and membership revocation."""

import asyncio
import os
from uuid import uuid4

import psycopg
import pytest

from app.foundation import documents
from app.foundation.repository import migrate

DSN = os.getenv("FOUNDATION_TEST_DSN", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


@pytest.fixture
def client():
    migrate(DSN)
    return documents.AsyncClient(dsn=DSN)


@pytest.mark.asyncio
async def test_parallel_editorial_commands_are_atomic_and_receipted(client):
    namespace = str(uuid4())
    counter = client.collection("cutover-tests").document(namespace)
    await counter.set({"count": 0})

    @documents.async_transactional
    async def increment(tx, command):
        receipt = counter.collection("receipts").document(command)
        if (await receipt.get(transaction=tx)).exists:
            return
        tx.update(counter, {"count": documents.Increment(1)})
        tx.set(receipt, {"complete": True})

    await asyncio.gather(*(increment(client.transaction(), str(n // 2)) for n in range(20)))
    assert (await counter.get()).to_dict()["count"] == 10
    assert len(await counter.collection("receipts").get()) == 10


@pytest.mark.asyncio
async def test_project_membership_revocation_reaches_shared_authority(client):
    project = uuid4().int % (2**31)
    ref = client.collection("projects").document(str(project))
    await ref.set(
        {
            "name": "Cutover test",
            "state": "active",
            "owner_email": "owner@example.test",
            "member_emails": ["editor@example.test"],
        }
    )
    await ref.update({"member_emails": []})
    with psycopg.connect(DSN) as conn:
        assert conn.execute(
            "SELECT email,role FROM project_members WHERE project_id=%s", (project,)
        ).fetchall() == [("owner@example.test", "owner")]
        assert conn.execute(
            "SELECT name,state FROM projects WHERE id=%s", (project,)
        ).fetchone() == ("Cutover test", "active")
    await ref.update({"state": "deleted"})
    with psycopg.connect(DSN) as conn:
        assert (
            conn.execute("SELECT state FROM projects WHERE id=%s", (project,)).fetchone()[0]
            == "deleted"
        )


@pytest.mark.asyncio
async def test_failed_transaction_cannot_publish_partial_receipt(client):
    ref = client.collection("cutover-tests").document(str(uuid4()))

    @documents.async_transactional
    async def fail(tx):
        tx.set(ref, {"complete": True})
        raise ValueError("Rejected command")

    with pytest.raises(ValueError):
        await fail(client.transaction())
    assert not (await ref.get()).exists
