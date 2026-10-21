"""Durable bounded work queue using PostgreSQL leases and fenced completion."""

from __future__ import annotations

import re
from typing import Protocol
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .repository import Conflict, fingerprint


class JobQueue(Protocol):
    def claim(self, lease_seconds: int = 120) -> dict | None: ...
    def finish(self, job_id: UUID, token: UUID, result: dict) -> bool: ...


class PostgresJobs:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def enqueue(
        self, project_id: int, kind: str, payload: dict, dedup_key: str, max_attempts: int = 3
    ) -> UUID:
        if not kind or not dedup_key or not 1 <= max_attempts <= 10:
            raise ValueError("Job kind, dedup key and 1..10 attempts required")
        fingerprint(payload)
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            conn.execute(
                """INSERT INTO jobs(id,project_id,kind,payload,dedup_key,max_attempts)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (uuid4(), project_id, kind, Jsonb(payload), dedup_key, max_attempts),
            )
            row = conn.execute(
                "SELECT * FROM jobs WHERE project_id=%s AND kind=%s AND dedup_key=%s",
                (project_id, kind, dedup_key),
            ).fetchone()
            assert row is not None
            if row["payload"] != payload or row["max_attempts"] != max_attempts:
                raise Conflict("Job key reused with changed payload or retry policy")
            return row["id"]

    def claim(self, lease_seconds: int = 120, kinds: list[str] | None = None) -> dict | None:
        if not 10 <= lease_seconds <= 3600:
            raise ValueError("Lease must be between 10 and 3600 seconds")
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            # Reaping and claiming in one transaction prevents abandoned running jobs.
            conn.execute("""
                UPDATE jobs SET state=CASE
                    WHEN cancel_requested THEN 'cancelled'
                    WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END,
                    lease_token=NULL, lease_until=NULL, error_code='lease_expired'
                WHERE state='running' AND lease_until < clock_timestamp()
            """)
            return conn.execute(
                """WITH candidate AS (
                    SELECT id FROM jobs WHERE state='queued' AND NOT cancel_requested
                      AND available_at <= clock_timestamp() AND attempts < max_attempts
                      AND (%s::text[] IS NULL OR kind=ANY(%s::text[]))
                    ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE jobs SET state='running', attempts=attempts+1, lease_token=%s,
                    lease_until=clock_timestamp() + (%s * interval '1 second')
                FROM candidate WHERE jobs.id=candidate.id RETURNING jobs.*""",
                (kinds, kinds, uuid4(), lease_seconds),
            ).fetchone()

    def heartbeat(self, job_id: UUID, token: UUID, lease_seconds: int = 120) -> bool:
        if not 10 <= lease_seconds <= 3600:
            raise ValueError("Lease must be between 10 and 3600 seconds")
        with psycopg.connect(self._dsn) as conn:
            return bool(
                conn.execute(
                    """UPDATE jobs SET lease_until=clock_timestamp() + (%s * interval '1 second')
                   WHERE id=%s AND lease_token=%s AND state='running'
                   AND NOT cancel_requested AND lease_until > clock_timestamp()""",
                    (lease_seconds, job_id, token),
                ).rowcount
            )

    def finish(self, job_id: UUID, token: UUID, result: dict) -> bool:
        fingerprint(result)
        with psycopg.connect(self._dsn) as conn:
            return bool(
                conn.execute(
                    """UPDATE jobs SET state=CASE WHEN cancel_requested THEN 'cancelled'
                        ELSE 'succeeded' END,
                    result=CASE WHEN cancel_requested THEN NULL ELSE %s END,
                    lease_token=NULL, lease_until=NULL
                   WHERE id=%s AND lease_token=%s AND state='running'
                     AND lease_until > clock_timestamp()""",
                    (Jsonb(result), job_id, token),
                ).rowcount
            )

    def fail(self, job_id: UUID, token: UUID, error_code: str, retry: bool = True) -> bool:
        if not re.fullmatch(r"[a-z0-9_]{1,100}", error_code):
            raise ValueError("Use a short sanitized error code, not a provider response")
        with psycopg.connect(self._dsn) as conn:
            return bool(
                conn.execute(
                    """UPDATE jobs SET state=CASE WHEN cancel_requested THEN 'cancelled'
                    WHEN %s AND attempts < max_attempts THEN 'queued' ELSE 'failed' END,
                    error_code=%s, lease_token=NULL, lease_until=NULL,
                    available_at=clock_timestamp() + interval '5 seconds'
                   WHERE id=%s AND lease_token=%s AND state='running'
                     AND lease_until > clock_timestamp()""",
                    (retry, error_code, job_id, token),
                ).rowcount
            )

    def cancel(self, project_id: int, job_id: UUID) -> bool:
        with psycopg.connect(self._dsn) as conn:
            return bool(
                conn.execute(
                    """UPDATE jobs SET cancel_requested=true,
                    state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END
                   WHERE id=%s AND project_id=%s AND state IN ('queued','running')""",
                    (job_id, project_id),
                ).rowcount
            )
