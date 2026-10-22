"""Transactional export requests and project-scoped artifact metadata."""

from typing import Literal
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import Field

from ..evidence.contracts import EvidenceError
from ..inference.contracts import Contract, fingerprint
from ..timeline.store import TimelineStore
from .formats import VERSION, validated


class ExportRequest(Contract):
    command_id: UUID
    format: Literal["native", "fcp7"]
    revision: int = Field(ge=1)


class ExportStore(TimelineStore):
    def enqueue_export(self, project: int, key: str, actor: str, command: ExportRequest) -> dict:
        request = {
            "sequence_id": key,
            "export": command.model_dump(mode="json"),
            "version": VERSION,
        }
        with self.connection() as conn:
            self.authorize_writer(conn, project, actor)
            replay = self.receipt(conn, project, actor, command.command_id, request)
            if replay:
                return replay
            snapshot = self.read(project, key, command.revision)
            validated(snapshot["body"])
            payload = {
                "sequence_id": key,
                "revision": command.revision,
                "format": command.format,
                "snapshot_sha256": fingerprint(snapshot["body"]),
                "version": VERSION,
            }
            job_id = uuid4()
            conn.execute(
                "INSERT INTO jobs(id,project_id,kind,payload,dedup_key,max_attempts) "
                "VALUES (%s,%s,'timeline_export',%s,%s,3)",
                (job_id, project, Jsonb(payload), str(job_id)),
            )
            result = {"job_id": str(job_id), "revision": command.revision, "format": command.format}
            self.remember(conn, project, actor, command.command_id, request, result)
            return result

    def export_job(self, project: int, job_id: UUID) -> dict:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT id,state,payload,result,error_code,cancel_requested,created_at "
                "FROM jobs WHERE project_id=%s AND id=%s AND kind='timeline_export'",
                (project, job_id),
            ).fetchone()
            if not row:
                raise EvidenceError("export_not_found")
            return row

    def exports(self, project: int, key: str) -> list[dict]:
        with self.connection() as conn:
            return conn.execute(
                "SELECT id,state,payload,result,error_code,created_at FROM jobs "
                "WHERE project_id=%s AND kind='timeline_export' AND payload->>'sequence_id'=%s "
                "ORDER BY created_at DESC LIMIT 30",
                (project, key),
            ).fetchall()
