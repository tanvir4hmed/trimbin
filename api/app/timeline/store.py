"""Reuse operational revisions/receipts; source and selection snapshots stay pinned."""

from uuid import UUID

from ..config import Settings
from ..evidence.contracts import EvidenceError
from ..evidence.store import EvidenceStore
from ..foundation.repository import Conflict, PostgresRepository, fingerprint
from ..media.files import MediaError, MediaPaths
from .contracts import Save, conform

KIND = "canonical_timeline"


class TimelineStore(EvidenceStore):
    def save(self, project: int, sequence_id: str, actor: str, command: Save) -> dict:
        request = {"timeline": sequence_id, "command": command.model_dump(mode="json")}
        with self.connection() as conn:
            self.authorize_writer(conn, project, actor)
            replay = self.receipt(conn, project, actor, command.command_id, request)
            if replay:
                return replay
            # Lock the same sequence before reading its prior pinned selections.
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"timeline/{project}/{sequence_id}",),
            )
            prior = conn.execute(
                "SELECT revision,body FROM state_documents WHERE project_id=%s "
                "AND kind=%s AND document_id=%s FOR UPDATE",
                (project, KIND, sequence_id),
            ).fetchone()
            if (prior["revision"] if prior else 0) != command.expected_revision:
                raise Conflict("Timeline changed; retain draft and reload explicitly")
            evidence = self.current(conn, project)
            selected = {s["selection_id"]: s for s in evidence["body"]["selections"]}
            if prior:
                for entry in prior["body"]["clips"]:
                    selected.setdefault(entry["selection_id"], entry["evidence"])
            # Restore pinned evidence from immutable history even after removing a selection.
            missing = list({str(c.selection_id) for c in command.clips} - selected.keys())
            if missing:
                historic = conn.execute(
                    "SELECT DISTINCT ON (c->>'selection_id') c->'evidence' AS evidence "
                    "FROM state_versions v CROSS JOIN LATERAL "
                    "jsonb_array_elements(v.body->'clips') c WHERE v.project_id=%s "
                    "AND v.kind=%s AND v.document_id=%s AND c->>'selection_id'=ANY(%s) "
                    "ORDER BY c->>'selection_id',v.revision DESC",
                    (project, KIND, sequence_id, missing),
                ).fetchall()
                selected.update({r["evidence"]["selection_id"]: r["evidence"] for r in historic})
            clips, start = [], 0
            for clip in command.clips:
                pinned = selected.get(str(clip.selection_id))
                if not pinned or pinned["source_id"] != str(clip.source_id):
                    raise EvidenceError("selected_evidence_not_found")
                source = self.source(conn, project, clip.source_id)
                if source["fingerprint"] != pinned["sha256"]:
                    raise EvidenceError("source_version_changed")
                key = f"{clip.source_id}/{source['fingerprint']}"
                timing = conn.execute(
                    "SELECT body FROM state_documents WHERE project_id=%s "
                    "AND kind='source_timing' AND document_id=%s",
                    (project, key),
                ).fetchone()
                if not timing:
                    raise EvidenceError("source_timing_not_verified")
                try:
                    entry = conform(clip, timing["body"], command.sequence, start)
                except ValueError as exc:
                    raise EvidenceError(str(exc)) from exc
                entry["evidence"] = pinned
                clips.append(entry)
                start += entry["duration_frames"]
            body = {
                "schema_version": "timeline-v1",
                "sequence": command.sequence.model_dump(mode="json"),
                "clips": clips,
                "duration_frames": start,
                "editor_approved": True,
                "export_acceptance": "pending_phases_7_8",
            }
            # Reuse the repository's atomic state/version/outbox writes. Its receipt hashes the
            # compiled snapshot; replace that hash with the original command for exact retries.
            result = PostgresRepository(self.dsn).save(
                project,
                KIND,
                sequence_id,
                command.expected_revision,
                body,
                actor,
                command.command_id,
                connection=conn,
            )
            conn.execute(
                "UPDATE command_receipts SET request_hash=%s WHERE project_id=%s "
                "AND actor=%s AND command_id=%s",
                (fingerprint(request), project, actor, command.command_id),
            )
            return result

    def read(self, project: int, sequence_id: str, revision: int | None = None) -> dict:
        with self.connection() as conn:
            if revision is None:
                row = conn.execute(
                    "SELECT revision,body FROM state_documents WHERE project_id=%s "
                    "AND kind=%s AND document_id=%s",
                    (project, KIND, sequence_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT revision,body FROM state_versions WHERE project_id=%s "
                    "AND kind=%s AND document_id=%s AND revision=%s",
                    (project, KIND, sequence_id, revision),
                ).fetchone()
            if not row:
                if revision is not None:
                    raise EvidenceError("timeline_revision_not_found")
                return {"revision": 0, "body": None}
            return row

    def history(self, project: int, sequence_id: str, before: int) -> list[dict]:
        with self.connection() as conn:
            return conn.execute(
                "SELECT revision,actor,created_at FROM state_versions "
                "WHERE project_id=%s AND kind=%s AND document_id=%s AND revision<%s "
                "ORDER BY revision DESC LIMIT 30",
                (project, KIND, sequence_id, before),
            ).fetchall()

    def availability(self, project: int, snapshot: dict, config: Settings) -> dict:
        unavailable = {}
        for clip in (snapshot.get("body") or {}).get("clips", []):
            source_id = clip["source_id"]
            if source_id in unavailable:
                continue
            try:
                with self.connection() as conn:
                    row = self.source(conn, project, UUID(source_id))
                if row["fingerprint"] != clip["source"]["sha256"]:
                    raise EvidenceError("source_version_changed")
                MediaPaths(config).resolve(project, row["root_alias"], row["relative_path"])
                unavailable[source_id] = None
            except (EvidenceError, MediaError, OSError) as exc:
                unavailable[source_id] = getattr(exc, "code", "source_unavailable")
        return {
            **snapshot,
            "source_errors": unavailable,
            "integrity": "Registry hash and path check only; export must rehash originals.",
        }
