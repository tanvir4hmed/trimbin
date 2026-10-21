"""Atomic editorial revisions and fenced complete-generation publication."""

from __future__ import annotations

from fractions import Fraction
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..foundation.repository import Conflict, fingerprint
from ..inference.contracts import TaskOutput, TaskRequest
from ..media.store import MediaStore
from .contracts import EditCommand, EvidenceError, Note

KIND = "evidence_workspace"
EMPTY = {"heads": {}, "notes": [], "corrections": {}, "selections": [], "placements": {}}
MAX_ITEMS = 5000


class EvidenceStore:
    def __init__(self, dsn: str):
        if not dsn:
            raise EvidenceError("evidence_not_configured")
        self.dsn = dsn

    def connection(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    @staticmethod
    def authorize_writer(conn, project: int, actor: str) -> None:
        membership = conn.execute(
            "SELECT role FROM project_members WHERE project_id=%s AND email=%s FOR SHARE",
            (project, actor.lower()),
        ).fetchone()
        if not membership or membership["role"] not in {"owner", "editor"}:
            raise EvidenceError("project_not_found")

    @staticmethod
    def current(conn, project: int, *, lock: bool = False) -> dict:
        if lock:
            conn.execute(
                "INSERT INTO state_documents(project_id,kind,document_id,body) "
                "VALUES (%s,%s,'current',%s) ON CONFLICT DO NOTHING",
                (project, KIND, Jsonb(EMPTY)),
            )
        row = conn.execute(
            "SELECT revision,body FROM state_documents WHERE project_id=%s AND kind=%s "
            "AND document_id='current'" + (" FOR UPDATE" if lock else ""),
            (project, KIND),
        ).fetchone()
        return row or {"revision": 0, "body": {**EMPTY}}

    @staticmethod
    def receipt(conn, project: int, actor: str, command: UUID, request: dict) -> dict | None:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"{project}/{actor}/{command}",),
        )
        row = conn.execute(
            "SELECT request_hash,result FROM command_receipts "
            "WHERE project_id=%s AND actor=%s AND command_id=%s",
            (project, actor, command),
        ).fetchone()
        if row and row["request_hash"] != fingerprint(request):
            raise Conflict("Command reused with different input")
        return {**row["result"], "replayed": True} if row else None

    @staticmethod
    def remember(conn, project, actor, command, request, result):
        conn.execute(
            "INSERT INTO command_receipts VALUES (%s,%s,%s,%s,%s)",
            (project, actor, command, fingerprint(request), Jsonb(result)),
        )

    @staticmethod
    def write(conn, project: int, current: dict, actor: str) -> dict:
        body, revision, event = current["body"], current["revision"] + 1, uuid4()
        if len(body["corrections"]) + len(body["notes"]) > MAX_ITEMS:
            raise EvidenceError("workspace_item_limit")
        conn.execute(
            "UPDATE state_documents SET revision=%s,body=%s "
            "WHERE project_id=%s AND kind=%s AND document_id='current'",
            (revision, Jsonb(body), project, KIND),
        )
        conn.execute(
            "INSERT INTO state_versions(project_id,kind,document_id,revision,body,actor) "
            "VALUES (%s,%s,'current',%s,%s,%s)",
            (project, KIND, revision, Jsonb(body), actor),
        )
        conn.execute(
            "INSERT INTO outbox(event_id,project_id,payload) VALUES (%s,%s,%s)",
            (event, project, Jsonb({"kind": KIND, "revision": revision})),
        )
        return {"revision": revision, "event_id": str(event), "replayed": False}

    @staticmethod
    def source(conn, project: int, source_id: UUID) -> dict:
        row = conn.execute(
            "SELECT s.*,j.state FROM media_sources s JOIN jobs j ON j.id=s.job_id "
            "WHERE s.project_id=%s AND s.id=%s",
            (project, source_id),
        ).fetchone()
        if not row or row["state"] != "succeeded":
            raise EvidenceError("indexed_source_not_found")
        duration = row["metadata"]["duration"]
        exact = Fraction(duration["numerator"], duration["denominator"]) * 1_000_000
        row["duration_us"] = -(-exact.numerator // exact.denominator)
        return row

    @classmethod
    def validate_note(cls, conn, project, note: Note) -> dict:
        source = cls.source(conn, project, note.source_id)
        if note.end_us > source["duration_us"]:
            raise EvidenceError("range_outside_source")
        return source

    @staticmethod
    def item(conn, project, item_id) -> dict:
        row = conn.execute(
            "SELECT body FROM evidence_items WHERE project_id=%s AND id=%s", (project, item_id)
        ).fetchone()
        if not row:
            raise EvidenceError("evidence_item_not_found")
        return row["body"]

    @staticmethod
    def effective(item: dict, body: dict) -> dict:
        correction = body["corrections"].get(item["id"], {})
        return {**item, **correction, "corrected": bool(correction)}

    @classmethod
    def rows(cls, conn, project: int, current: dict) -> list[dict]:
        body = current["body"]
        runs = [UUID(v) for v in body["heads"].values()]
        pinned = {UUID(v) for v in [*body["notes"], *body["corrections"]]}
        rows = conn.execute(
            "SELECT i.body, EXISTS(SELECT 1 FROM evidence_run_items r WHERE "
            "r.project_id=i.project_id AND r.item_id=i.id AND r.run_id=ANY(%s::uuid[])) AS active "
            "FROM evidence_items i WHERE i.project_id=%s AND (i.id=ANY(%s::uuid[]) OR "
            "EXISTS(SELECT 1 FROM evidence_run_items r WHERE r.project_id=i.project_id "
            "AND r.item_id=i.id AND r.run_id=ANY(%s::uuid[]))) ORDER BY i.id LIMIT %s",
            (runs, project, list(pinned), runs, MAX_ITEMS + 1),
        ).fetchall()
        if len(rows) > MAX_ITEMS:
            raise EvidenceError("workspace_item_limit")
        return [
            {
                **cls.effective(r["body"], body),
                "current": r["active"] or r["body"]["id"] in body["notes"],
            }
            for r in rows
        ]

    def snapshot(self, project: int) -> dict:
        with self.connection() as conn:
            # Pin all reads to one committed snapshot, without holding writer locks.
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            state = self.current(conn, project)
            rows = self.rows(conn, project, state)
            return {
                "revision": state["revision"],
                "items": rows,
                "selections": state["body"]["selections"],
                "placements": state["body"]["placements"],
                "review_counts": {
                    decision: sum(
                        r.get("decision", "uncertain") == decision for r in rows if r["current"]
                    )
                    for decision in ("accepted", "uncertain", "retracted")
                },
                "quality_status": "not_evaluated",
            }

    def edit(self, project: int, actor: str, command: EditCommand) -> dict:
        request = command.model_dump(mode="json")
        with self.connection() as conn:
            self.authorize_writer(conn, project, actor)
            replay = self.receipt(conn, project, actor, command.command_id, request)
            if replay:
                return replay
            state = self.current(conn, project, lock=True)
            if state["revision"] != command.expected_revision:
                raise Conflict("Workspace revision changed; reload and retain your draft")
            body, item_id = state["body"], str(command.item_id) if command.item_id else None
            if command.operation == "note":
                if command.note is None:
                    raise EvidenceError("note_required")
                source = self.validate_note(conn, project, command.note)
                new_id = str(uuid5(NAMESPACE_URL, f"{project}/{actor}/{command.command_id}"))
                item = {
                    **command.note.model_dump(mode="json"),
                    "id": new_id,
                    "sha256": source["fingerprint"],
                    "origin": "human",
                    "actor": actor,
                    "decision": command.decision,
                    "confidence": None,
                    "citations": [],
                }
                conn.execute(
                    "INSERT INTO evidence_items VALUES (%s,%s,%s,%s)",
                    (project, UUID(new_id), command.note.source_id, Jsonb(item)),
                )
                body["notes"].append(new_id)
            elif command.operation in {"correct", "select"}:
                if not item_id:
                    raise EvidenceError("item_required")
                item = self.effective(self.item(conn, project, command.item_id), body)
                source = self.source(conn, project, UUID(item["source_id"]))
                if source["fingerprint"] != item["sha256"]:
                    raise EvidenceError("source_version_changed")
                if command.operation == "correct":
                    correction = {
                        **body["corrections"].get(item_id, {}),
                        "decision": command.decision,
                        "editor": actor,
                        "correction_revision": state["revision"] + 1,
                    }
                    if command.note:
                        if str(command.note.source_id) != item["source_id"]:
                            raise EvidenceError("correction_cannot_change_source")
                        self.validate_note(conn, project, command.note)
                        correction.update(command.note.model_dump(mode="json"))
                    body["corrections"][item_id] = correction
                else:
                    if item["decision"] == "retracted":
                        raise EvidenceError("cannot_select_retracted_evidence")
                    if len(body["selections"]) >= 256:
                        raise EvidenceError("selection_limit")
                    body["selections"].append(
                        {
                            **item,
                            "selection_id": str(command.command_id),
                            "evidence_revision": state["revision"],
                        }
                    )
            elif command.operation == "unselect":
                if not item_id or not any(s["selection_id"] == item_id for s in body["selections"]):
                    raise EvidenceError("selection_not_found")
                body["selections"] = [s for s in body["selections"] if s["selection_id"] != item_id]
            elif command.operation == "place":
                if not command.source_id:
                    raise EvidenceError("source_required")
                self.source(conn, project, command.source_id)
                body["placements"][str(command.source_id)] = {
                    "scene": command.scene,
                    "shot": command.shot,
                    "take": command.take,
                    "actor": actor,
                    "revision": state["revision"] + 1,
                }
            result = self.write(conn, project, state, actor)
            self.remember(conn, project, actor, command.command_id, request, result)
            return result

    def enqueue(self, project: int, actor: str, command: dict, config_identity: dict) -> dict:
        request = {"command": command, "config": config_identity}
        with self.connection() as conn:
            self.authorize_writer(conn, project, actor)
            replay = self.receipt(conn, project, actor, UUID(command["command_id"]), request)
            if replay:
                return replay
            state = self.current(conn, project, lock=True)
            if state["revision"] != command["expected_revision"]:
                raise Conflict("Workspace revision changed")
            plan = {
                **command,
                "config": config_identity,
                "project_id": project,
                "evidence_revision": state["revision"],
                "actor": actor,
            }
            if command["task"] in {"visual", "slate"}:
                source = self.source(conn, project, UUID(command["source_id"]))
                plan["sources"] = [
                    {
                        "id": str(source["id"]),
                        "sha256": source["fingerprint"],
                        "duration_us": source["duration_us"],
                    }
                ]
                scope = f"{source['id']}:{command['task']}"
            else:
                selected = state["body"]["selections"]
                if not selected or len(selected) > 32:
                    raise EvidenceError("select_between_1_and_32_ranges")
                plan["selections"] = selected
                sources = {}
                for item in selected:
                    source = self.source(conn, project, UUID(item["source_id"]))
                    if source["fingerprint"] != item["sha256"]:
                        raise EvidenceError("source_version_changed")
                    sources[item["source_id"]] = {
                        "id": item["source_id"],
                        "sha256": item["sha256"],
                        "duration_us": source["duration_us"],
                    }
                plan["sources"] = list(sources.values())
                scope = f"review:{command['task']}"
            run_id, job_id = uuid4(), uuid4()
            conn.execute(
                "INSERT INTO jobs(id,project_id,kind,payload,dedup_key,max_attempts) "
                "VALUES (%s,%s,'evidence_analysis',%s,%s,1)",
                (job_id, project, Jsonb({"run_id": str(run_id)}), str(run_id)),
            )
            conn.execute(
                "INSERT INTO evidence_runs(id,project_id,scope,task,mode,job_id,plan) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (run_id, project, scope, command["task"], command["mode"], job_id, Jsonb(plan)),
            )
            conn.execute(
                "INSERT INTO evidence_requests VALUES (%s,%s,%s) "
                "ON CONFLICT(project_id,scope) DO UPDATE SET latest_run=excluded.latest_run",
                (project, scope, run_id),
            )
            result = {"run_id": str(run_id), "job_id": str(job_id), "revision": state["revision"]}
            self.remember(conn, project, actor, UUID(command["command_id"]), request, result)
            return result

    def run(self, project: int, run_id: UUID) -> dict:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT r.*,j.state,j.error_code FROM evidence_runs r "
                "JOIN jobs j ON j.id=r.job_id WHERE r.project_id=%s AND r.id=%s",
                (project, run_id),
            ).fetchone()
            if not row:
                raise EvidenceError("analysis_run_not_found")
            return row

    def runs(self, project: int) -> list[dict]:
        with self.connection() as conn:
            return conn.execute(
                "SELECT r.id,r.task,r.mode,r.published,r.created_at,j.state,"
                "j.error_code FROM evidence_runs r JOIN jobs j ON j.id=r.job_id "
                "WHERE r.project_id=%s ORDER BY r.created_at DESC LIMIT 30",
                (project,),
            ).fetchall()

    def publish(self, job: dict, run: dict, records: list[dict]) -> None:
        if not records or any(r["status"] not in {"fixture", "validated"} for r in records):
            raise EvidenceError("incomplete_analysis_generation")
        expected_status = "fixture" if run["mode"] == "fixture" else "validated"
        if any(r["status"] != expected_status for r in records):
            raise EvidenceError("analysis_mode_mismatch")
        project = run["project_id"]
        expected_windows = []
        if run["task"] in {"visual", "slate"}:
            plan = run["plan"]
            start, duration = 0, plan["sources"][0]["duration_us"]
            length, overlap = plan["window_seconds"] * 1000000, plan["overlap_seconds"] * 1000000
            if overlap >= length:
                raise EvidenceError("invalid_analysis_windows")
            while start < duration:
                end = min(duration, start + length)
                expected_windows.append((start, end))
                if len(expected_windows) > 256:
                    raise EvidenceError("analysis_window_limit")
                if end == duration:
                    break
                start = end - overlap
        if len(records) != (len(expected_windows) if expected_windows else 1):
            raise EvidenceError("incomplete_analysis_generation")
        for index, record in enumerate(records):
            request = TaskRequest.model_validate(record["input_manifest"])
            if (
                request.project_id != project
                or request.task != run["task"]
                or [s.model_dump(mode="json") for s in request.sources] != run["plan"]["sources"]
            ):
                raise EvidenceError("analysis_manifest_mismatch")
            if expected_windows and [(w.start_us, w.end_us) for w in request.windows] != [
                expected_windows[index]
            ]:
                raise EvidenceError("analysis_window_mismatch")
            TaskOutput.model_validate(record["output"]).validate_for(request)
        with self.connection() as conn:
            if not MediaStore.owned(conn, job):
                raise EvidenceError("lease_lost")
            state = self.current(conn, project, lock=True)
            latest = conn.execute(
                "SELECT latest_run FROM evidence_requests WHERE project_id=%s "
                "AND scope=%s FOR UPDATE",
                (project, run["scope"]),
            ).fetchone()
            active = latest["latest_run"] == run["id"]
            source_hashes = {s["id"]: s["sha256"] for s in run["plan"]["sources"]}
            for record in records:
                for finding in record["output"]["findings"]:
                    identity = {**finding, "generation": record["generation"]}
                    identity["sha256"] = source_hashes[finding["source_id"]]
                    item_id = uuid5(NAMESPACE_URL, f"{project}/{fingerprint(identity)}")
                    item = {
                        **finding,
                        **identity,
                        "id": str(item_id),
                        "origin": run["mode"],
                        "decision": "uncertain",
                    }
                    conn.execute(
                        "INSERT INTO evidence_items VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (project, item_id, UUID(finding["source_id"]), Jsonb(item)),
                    )
                    conn.execute(
                        "INSERT INTO evidence_run_items VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                        (run["id"], project, item_id),
                    )
            conn.execute(
                "UPDATE evidence_runs SET result=%s,published=%s WHERE id=%s",
                (Jsonb({"records": records, "quality_status": "not_evaluated"}), active, run["id"]),
            )
            if active:
                state["body"]["heads"][run["scope"]] = str(run["id"])
                self.rows(conn, project, state)  # Refuse a partially visible over-limit workspace.
                self.write(conn, project, state, "analysis-worker")
            conn.execute(
                "UPDATE jobs SET state='succeeded',lease_token=NULL,lease_until=NULL,"
                "result=%s,error_code=NULL WHERE id=%s",
                (Jsonb({"run_id": str(run["id"]), "published": active}), job["id"]),
            )
