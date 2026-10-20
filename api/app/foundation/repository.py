"""Transactional revisions, receipts and outbox, with no cloud SDK imports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class Conflict(Exception):
    """A stale revision or changed idempotency body."""


class StateRepository(Protocol):
    def save(
        self,
        project_id: int,
        kind: str,
        document_id: str,
        expected: int,
        body: dict,
        actor: str,
        command_id: UUID,
    ) -> dict: ...


def fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def migrate(dsn: str) -> None:
    schema = Path(__file__).with_name("schema.sql").read_text("utf-8")
    digest = hashlib.sha256(schema.encode()).hexdigest()
    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(72819412)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS foundation_migrations (
                version integer PRIMARY KEY, checksum text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
            )
        """)
        previous = conn.execute(
            "SELECT checksum FROM foundation_migrations WHERE version = 1"
        ).fetchone()
        if previous:
            if previous[0] != digest:
                raise RuntimeError("Applied foundation migration checksum changed")
            return
        conn.execute(schema)
        conn.execute(
            "INSERT INTO foundation_migrations(version, checksum) VALUES (1, %s)", (digest,)
        )


class PostgresRepository:
    """Each operation owns a transaction. Callers must authorize project/actor first."""

    def __init__(self, dsn: str):
        self._dsn = dsn

    def save(
        self,
        project_id: int,
        kind: str,
        document_id: str,
        expected: int,
        body: dict,
        actor: str,
        command_id: UUID,
    ) -> dict:
        if expected < 0 or not actor or not kind or not document_id:
            raise ValueError("An actor, document identity and nonnegative revision are required")
        request_hash = fingerprint([kind, document_id, expected, body])
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            # Serializes concurrent replays even when they target different documents.
            lock_key = f"{project_id}/{actor}/{command_id}"
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
            receipt = conn.execute(
                """SELECT request_hash, result FROM command_receipts
                   WHERE project_id=%s AND actor=%s AND command_id=%s""",
                (project_id, actor, command_id),
            ).fetchone()
            if receipt:
                if receipt["request_hash"] != request_hash:
                    raise Conflict("Command ID reused with a different request")
                return {**receipt["result"], "replayed": True}
            identity = (project_id, kind, document_id)
            conn.execute(
                """INSERT INTO state_documents(project_id, kind, document_id)
                   VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                identity,
            )
            current = conn.execute(
                """SELECT revision FROM state_documents
                   WHERE project_id=%s AND kind=%s AND document_id=%s FOR UPDATE""",
                identity,
            ).fetchone()
            assert current is not None
            if current["revision"] != expected:
                raise Conflict(f"Expected revision {expected}; current {current['revision']}")
            revision, event_id = expected + 1, uuid4()
            conn.execute(
                """UPDATE state_documents SET revision=%s, body=%s
                   WHERE project_id=%s AND kind=%s AND document_id=%s""",
                (revision, Jsonb(body), *identity),
            )
            conn.execute(
                """INSERT INTO state_versions
                   (project_id,kind,document_id,revision,body,actor) VALUES (%s,%s,%s,%s,%s,%s)""",
                (*identity, revision, Jsonb(body), actor),
            )
            result = {"revision": revision, "event_id": str(event_id)}
            conn.execute(
                "INSERT INTO command_receipts VALUES (%s,%s,%s,%s,%s)",
                (project_id, actor, command_id, request_hash, Jsonb(result)),
            )
            event = {
                "kind": kind,
                "document_id": document_id,
                "revision": revision,
                "actor": actor,
                "body": body,
            }
            conn.execute(
                "INSERT INTO outbox(event_id,project_id,payload) VALUES (%s,%s,%s)",
                (event_id, project_id, Jsonb(event)),
            )
            return {**result, "replayed": False}

    def read(self, project_id: int, kind: str, document_id: str) -> dict | None:
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            return conn.execute(
                """SELECT revision, body FROM state_documents
                   WHERE project_id=%s AND kind=%s AND document_id=%s""",
                (project_id, kind, document_id),
            ).fetchone()

    def pending_events(self, limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise ValueError("Outbox batch must be between 1 and 1000")
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            return conn.execute(
                """SELECT event_id, project_id, payload FROM outbox
                   WHERE delivered_at IS NULL ORDER BY created_at LIMIT %s""",
                (limit,),
            ).fetchall()

    def acknowledge_event(self, event_id: UUID) -> None:
        # Delivery is at least once. The receiving projection deduplicates by event_id.
        with psycopg.connect(self._dsn) as conn:
            conn.execute(
                "UPDATE outbox SET delivered_at=clock_timestamp() WHERE event_id=%s",
                (event_id,),
            )
