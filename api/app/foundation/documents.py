"""PostgreSQL document operations preserving editorial revisions and command receipts.

There is no remote document database. Existing editorial services retain their
document identities while transactions, membership and jobs share PostgreSQL.
"""

from __future__ import annotations

import copy
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb


def encode(value):
    if isinstance(value, datetime):
        return {"$trimbin_datetime": value.isoformat()}
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    return value


def decode(value):
    if isinstance(value, dict):
        if set(value) == {"$trimbin_datetime"}:
            return datetime.fromisoformat(value["$trimbin_datetime"])
        return {k: decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode(v) for v in value]
    return value


@dataclass
class Increment:
    value: int


@dataclass
class ArrayUnion:
    values: list


class Query:
    DESCENDING = "DESCENDING"


@dataclass
class Snapshot:
    reference: object
    data: dict | None

    @property
    def exists(self):
        return self.data is not None

    @property
    def id(self):
        return self.reference.id

    def to_dict(self):
        return copy.deepcopy(self.data)


class Transaction:
    def __init__(self, client):
        self.client = client
        self.connection = None
        self.writes = []

    def set(self, ref, body, merge=False):
        self.writes.append((ref, body, merge, False))

    def update(self, ref, body):
        self.writes.append((ref, body, True, True))

    def delete(self, ref):
        self.writes.append((ref, None, False, False))


def async_transactional(function):
    @wraps(function)
    async def run(transaction, *args, **kwargs):
        async with await psycopg.AsyncConnection.connect(transaction.client.dsn) as conn:
            transaction.connection = conn
            # One short editorial command at a time; readers stay nonblocking.
            await conn.execute("SELECT pg_advisory_xact_lock(83017410)")
            result = await function(transaction, *args, **kwargs)
            for ref, body, merge, required in transaction.writes:
                await ref._write(conn, body, merge, required)
            return result

    return run


class Document:
    def __init__(self, client, path):
        self.client, self.path = client, path
        self.id = path.rsplit("/", 1)[-1]

    def collection(self, name):
        return Collection(self.client, f"{self.path}/{name}")

    async def get(self, transaction=None):
        async with self.client.connection(transaction) as conn:
            result = await (
                await conn.execute(
                    "SELECT body FROM operational_documents WHERE path=%s", (self.path,)
                )
            ).fetchone()
        return Snapshot(self, decode(result[0]) if result else None)

    async def _write(self, conn, body, merge, required=False):
        if body is None:
            await conn.execute("DELETE FROM operational_documents WHERE path=%s", (self.path,))
            return
        old = await (
            await conn.execute(
                "SELECT body FROM operational_documents WHERE path=%s FOR UPDATE", (self.path,)
            )
        ).fetchone()
        if required and old is None:
            raise ValueError("Document does not exist")
        value = decode(old[0]) if old and merge else {}
        for key, item in body.items():
            parts = key.split(".") if merge else [key]
            node = value
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            leaf = parts[-1]
            if isinstance(item, Increment):
                node[leaf] = node.get(leaf, 0) + item.value
            elif isinstance(item, ArrayUnion):
                previous = list(node.get(leaf, []))
                node[leaf] = previous + [v for v in item.values if v not in previous]
            else:
                node[leaf] = copy.deepcopy(item)
        await conn.execute(
            "INSERT INTO operational_documents(path,body) VALUES (%s,%s) "
            "ON CONFLICT(path) DO UPDATE SET body=excluded.body,updated_at=clock_timestamp()",
            (self.path, Jsonb(encode(value))),
        )
        if self.path.startswith("projects/") and self.path.count("/") == 1:
            project = int(self.id)
            await conn.execute(
                "INSERT INTO projects(id,name,state) VALUES (%s,%s,%s) ON CONFLICT(id) "
                "DO UPDATE SET name=excluded.name,state=excluded.state",
                (project, value.get("name", ""), value.get("state", "active")),
            )
            emails = {email.lower(): "editor" for email in value.get("member_emails", [])}
            if value.get("owner_email"):
                emails[value["owner_email"].lower()] = "owner"
            await conn.execute("DELETE FROM project_members WHERE project_id=%s", (project,))
            for email, role in emails.items():
                await conn.execute(
                    "INSERT INTO project_members(project_id,email,role) VALUES (%s,%s,%s)",
                    (project, email, role),
                )

    async def set(self, body, merge=False):
        async with self.client.connection() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(83017410)")
            await self._write(conn, body, merge)

    async def update(self, body):
        async with self.client.connection() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(83017410)")
            await self._write(conn, body, True, True)

    async def delete(self):
        async with self.client.connection() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(83017410)")
            await self._write(conn, None, False)


class Collection:
    def __init__(self, client, path, filters=(), ordering=None, maximum=None):
        self.client, self.path = client, path
        self.filters, self.ordering, self.maximum = filters, ordering, maximum

    def document(self, identifier):
        return Document(self.client, f"{self.path}/{identifier}")

    def where(self, field, operator, value):
        if operator not in {"==", "in", "array_contains"}:
            raise ValueError("Unsupported document predicate")
        return Collection(
            self.client,
            self.path,
            (*self.filters, (field, operator, value)),
            self.ordering,
            self.maximum,
        )

    def order_by(self, field, direction="ASCENDING"):
        return Collection(self.client, self.path, self.filters, (field, direction), self.maximum)

    def limit(self, maximum):
        return Collection(self.client, self.path, self.filters, self.ordering, maximum)

    async def get(self, transaction=None):
        return [item async for item in self.stream(transaction)]

    async def stream(self, transaction=None):
        async with self.client.connection(transaction) as conn:
            cursor = await conn.execute(
                "SELECT path,body FROM operational_documents "
                "WHERE regexp_replace(path, '/[^/]+$', '')=%s",
                (self.path,),
            )
            records = await cursor.fetchall()
        result = []
        for path, raw in records:
            data = decode(raw)
            if all(
                (
                    data.get(field) == value
                    if op == "=="
                    else data.get(field) in value
                    if op == "in"
                    else value in data.get(field, [])
                )
                for field, op, value in self.filters
            ):
                result.append(Snapshot(Document(self.client, path), data))
        if self.ordering:
            field, direction = self.ordering
            result.sort(key=lambda r: r.data.get(field, 0), reverse=direction == Query.DESCENDING)
        for item in result[: self.maximum]:
            yield item


class AsyncClient:
    def __init__(self, project=None, *, dsn=None):
        from ..config import settings

        self.dsn = dsn or settings.database_url

    def collection(self, name):
        return Collection(self, name)

    def transaction(self):
        return Transaction(self)

    @asynccontextmanager
    async def connection(self, transaction=None):
        if transaction and transaction.connection:
            yield transaction.connection
        else:
            async with await psycopg.AsyncConnection.connect(self.dsn) as conn:
                yield conn

    async def get_all(self, refs):
        for ref in refs:
            yield await ref.get()
