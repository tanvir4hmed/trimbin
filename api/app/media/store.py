"""Project-scoped media state and filesystem/transaction recovery boundaries."""

from __future__ import annotations

import hashlib
import os
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .files import CHUNK_BYTES, MediaError, MediaPaths, media_filename, require_space, safe_path


class MediaStore:
    def __init__(self, dsn: str):
        if not dsn:
            raise MediaError("database_not_configured")
        self.dsn = dsn

    def connection(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def allowed(self, project: int, email: str, permission: str) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT m.role FROM project_members m JOIN projects p ON p.id=m.project_id "
                "WHERE m.project_id=%s AND m.email=%s AND p.state='active'",
                (project, email.lower()),
            ).fetchone()
        roles = {
            "read": {"owner", "editor", "viewer"},
            "write": {"owner", "editor"},
            "owner": {"owner"},
        }
        return bool(row and row["role"] in roles[permission])

    @staticmethod
    def ensure_project(conn, project: int) -> None:
        # Called only after the application's existing project authorization.
        conn.execute(
            "INSERT INTO projects(id,name) VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (project, f"Project {project}"),
        )

    def register(
        self, project: int, alias: str, relative: str, actor: str, source_id=None, editorial=False
    ) -> dict:
        with self.connection() as conn:
            self.ensure_project(conn, project)
            return self._register(conn, project, alias, relative, actor, source_id, editorial)

    @staticmethod
    def _register(
        conn, project: int, alias: str, relative: str, actor: str, source_id=None, editorial=False
    ) -> dict:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"media/{project}/{alias}/{relative}",),
        )
        existing = conn.execute(
            """SELECT * FROM media_sources
               WHERE project_id=%s AND root_alias=%s AND relative_path=%s""",
            (project, alias, relative),
        ).fetchone()
        if existing:
            return existing
        source_id, job_id = source_id or uuid4(), uuid4()
        conn.execute(
            """INSERT INTO jobs(id,project_id,kind,payload,dedup_key,max_attempts)
               VALUES (%s,%s,'media_index',%s,%s,3)""",
            (
                job_id,
                project,
                Jsonb({"source_id": str(source_id), "editorial_origin": editorial}),
                str(source_id),
            ),
        )
        return conn.execute(
            """INSERT INTO media_sources
               (id,project_id,root_alias,relative_path,filename,job_id,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (source_id, project, alias, relative, relative.rsplit("/", 1)[-1], job_id, actor),
        ).fetchone()

    def get(self, project: int, source_id: UUID) -> dict:
        with self.connection() as conn:
            row = conn.execute(
                """SELECT s.*,j.state,j.error_code,j.cancel_requested FROM media_sources s
                   JOIN jobs j ON j.id=s.job_id WHERE s.project_id=%s AND s.id=%s""",
                (project, source_id),
            ).fetchone()
        if row is None:
            raise MediaError("source_not_found")
        return row

    def listing(self, project: int, offset: int, limit: int) -> list[dict]:
        with self.connection() as conn:
            return conn.execute(
                """SELECT s.*,j.state,j.error_code,j.cancel_requested FROM media_sources s
                   JOIN jobs j ON j.id=s.job_id WHERE s.project_id=%s
                   ORDER BY s.created_at,s.id LIMIT %s OFFSET %s""",
                (project, limit, offset),
            ).fetchall()

    @staticmethod
    def owned(conn, job: dict) -> bool:
        return bool(
            conn.execute(
                """SELECT id FROM jobs WHERE id=%s AND lease_token=%s AND state='running'
                   AND NOT cancel_requested AND lease_until>clock_timestamp() FOR UPDATE""",
                (job["id"], job["lease_token"]),
            ).fetchone()
        )

    def stage(self, job: dict, stage: str) -> None:
        with self.connection() as conn:
            if not self.owned(conn, job):
                raise MediaError("lease_lost")
            conn.execute("UPDATE media_sources SET stage=%s WHERE job_id=%s", (stage, job["id"]))

    def publish(self, job: dict, fingerprint: str, metadata: dict, derivatives: dict) -> None:
        with self.connection() as conn:
            if not self.owned(conn, job):
                raise MediaError("lease_lost")
            # Serialize duplicate lookup/publication for identical project content.
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"fingerprint/{job['project_id']}/{fingerprint}",),
            )
            duplicate = conn.execute(
                """SELECT id FROM media_sources WHERE project_id=%s AND fingerprint=%s
                   AND job_id<>%s ORDER BY created_at,id LIMIT 1""",
                (job["project_id"], fingerprint, job["id"]),
            ).fetchone()
            conn.execute(
                """UPDATE media_sources SET fingerprint=%s,metadata=%s,derivatives=%s,
                   duplicate_of=%s,stage='ready' WHERE job_id=%s""",
                (
                    fingerprint,
                    Jsonb(metadata),
                    Jsonb(derivatives),
                    duplicate["id"] if duplicate else None,
                    job["id"],
                ),
            )
            conn.execute(
                """UPDATE jobs SET state='succeeded',lease_token=NULL,lease_until=NULL,
                   result=%s,error_code=NULL WHERE id=%s""",
                (Jsonb({"fingerprint": fingerprint}), job["id"]),
            )
            if not job["payload"].get("editorial_origin"):
                from ..foundation.editorial_bridge import enqueue_source

                enqueue_source(conn, job)

    def retry(self, project: int, source_id: UUID) -> None:
        with self.connection() as conn:
            row = conn.execute(
                """UPDATE jobs j SET state='queued',attempts=0,cancel_requested=false,
                   error_code=NULL,available_at=clock_timestamp()
                   FROM media_sources s WHERE s.job_id=j.id AND s.project_id=%s AND s.id=%s
                   AND j.state IN ('failed','cancelled') RETURNING j.id""",
                (project, source_id),
            ).fetchone()
            if row is None:
                raise MediaError("source_not_retryable")
            conn.execute("UPDATE media_sources SET stage='queued' WHERE id=%s", (source_id,))

    def relink(self, project: int, source_id: UUID, alias: str, relative: str, digest: str) -> None:
        with self.connection() as conn:
            row = conn.execute(
                """SELECT s.* FROM media_sources s JOIN jobs j ON s.job_id=j.id
                   WHERE s.project_id=%s AND s.id=%s AND j.state='succeeded' FOR UPDATE OF s""",
                (project, source_id),
            ).fetchone()
            if row is None or row["fingerprint"] != digest:
                raise MediaError("relink_fingerprint_mismatch")
            conflict = conn.execute(
                """SELECT id FROM media_sources WHERE project_id=%s AND root_alias=%s
                   AND relative_path=%s AND id<>%s""",
                (project, alias, relative, source_id),
            ).fetchone()
            if conflict:
                raise MediaError("relink_path_in_use")
            conn.execute(
                "UPDATE media_sources SET root_alias=%s,relative_path=%s,filename=%s WHERE id=%s",
                (alias, relative, relative.rsplit("/", 1)[-1], source_id),
            )

    def open_upload(self, project: int, filename: str, size: int, actor: str) -> dict:
        media_filename(filename)
        with self.connection() as conn:
            self.ensure_project(conn, project)
            conn.execute("SELECT id FROM projects WHERE id=%s FOR UPDATE", (project,))
            count = conn.execute(
                "SELECT count(*) AS n FROM media_uploads WHERE project_id=%s AND source_id IS NULL",
                (project,),
            ).fetchone()["n"]
            if count >= 10:
                raise MediaError("upload_limit_reached")
            return conn.execute(
                """INSERT INTO media_uploads(id,project_id,filename,expected_bytes,created_by)
                   VALUES (%s,%s,%s,%s,%s) RETURNING *""",
                (uuid4(), project, filename, size, actor),
            ).fetchone()

    @staticmethod
    def upload_row(conn, project: int, upload_id: UUID, actor: str) -> dict:
        row = conn.execute(
            """SELECT * FROM media_uploads WHERE project_id=%s AND id=%s AND created_by=%s
               FOR UPDATE""",
            (project, upload_id, actor),
        ).fetchone()
        if row is None:
            raise MediaError("upload_not_found")
        return row

    def upload_status(self, project: int, upload_id: UUID, actor: str) -> dict:
        with self.connection() as conn:
            return self.upload_row(conn, project, upload_id, actor)

    def pending_uploads(self, project: int, actor: str) -> list[dict]:
        with self.connection() as conn:
            return conn.execute(
                """SELECT * FROM media_uploads WHERE project_id=%s AND created_by=%s
                   AND source_id IS NULL ORDER BY created_at LIMIT 10""",
                (project, actor),
            ).fetchall()

    def append_upload(
        self,
        paths: MediaPaths,
        project: int,
        upload_id: UUID,
        actor: str,
        offset: int,
        data: bytes,
        reserve: int,
    ) -> dict:
        if not data or len(data) > CHUNK_BYTES:
            raise MediaError("invalid_chunk_size")
        with self.connection() as conn:
            row = self.upload_row(conn, project, upload_id, actor)
            if row["source_id"] or offset != row["received_bytes"]:
                raise MediaError("upload_offset_conflict")
            if offset + len(data) > row["expected_bytes"]:
                raise MediaError("upload_size_exceeded")
            if len(data) != min(CHUNK_BYTES, row["expected_bytes"] - offset):
                raise MediaError("invalid_chunk_size")
            target = safe_path(paths.staging, f"{upload_id}.part", exists=False)
            require_space(paths.staging, len(data), reserve)
            with target.open("r+b" if target.exists() else "w+b") as handle:
                handle.seek(0, 2)
                if handle.tell() < offset:
                    raise MediaError("upload_data_missing")
                # An earlier crash may have fsynced bytes before the DB commit.
                handle.truncate(offset)
                handle.seek(offset)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            return conn.execute(
                """UPDATE media_uploads SET received_bytes=%s,chunk_hashes=%s
                   WHERE id=%s RETURNING *""",
                (
                    offset + len(data),
                    Jsonb([*row["chunk_hashes"], hashlib.sha256(data).hexdigest()]),
                    upload_id,
                ),
            ).fetchone()

    def complete_upload(self, paths: MediaPaths, project: int, upload_id: UUID, actor: str) -> dict:
        with self.connection() as conn:
            row = self.upload_row(conn, project, upload_id, actor)
            if row["source_id"]:
                return row
            if row["received_bytes"] != row["expected_bytes"]:
                raise MediaError("upload_incomplete")
            relative = f"p{project}/{upload_id}/{row['filename']}"
            destination = paths.resolve(project, "uploads", relative, exists=False)
            destination.parent.mkdir(parents=True, exist_ok=True)
            pending = safe_path(paths.staging, f"{upload_id}.part", exists=False)
            if pending.exists():
                if destination.exists():
                    raise MediaError("upload_destination_conflict")
                # Roots must share a filesystem; atomic publication must not copy GBs.
                if pending.stat().st_size != row["expected_bytes"]:
                    raise MediaError("upload_incomplete")
                try:
                    pending.rename(destination)
                except OSError as exc:
                    raise MediaError("upload_promotion_failed") from exc
            elif not destination.exists() or destination.stat().st_size != row["expected_bytes"]:
                raise MediaError("upload_data_missing")
            # Existing destination is recovery from a rename before transaction commit.
            source = self._register(conn, project, "uploads", relative, actor)
            return conn.execute(
                "UPDATE media_uploads SET source_id=%s WHERE id=%s RETURNING *",
                (source["id"], upload_id),
            ).fetchone()

    def discard_upload(self, paths: MediaPaths, project: int, upload_id: UUID, actor: str) -> None:
        with self.connection() as conn:
            row = self.upload_row(conn, project, upload_id, actor)
            if row["source_id"]:
                raise MediaError("upload_already_completed")
            # Never delete a promoted original, including an interrupted completion.
            target = paths.resolve(
                project,
                "uploads",
                f"p{project}/{upload_id}/{row['filename']}",
                exists=False,
            )
            if target.exists():
                raise MediaError("upload_completion_pending")
            safe_path(paths.staging, f"{upload_id}.part", exists=False).unlink(missing_ok=True)
            conn.execute("DELETE FROM media_uploads WHERE id=%s", (upload_id,))
