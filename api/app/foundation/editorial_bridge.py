"""Transactional connection of one media identity to the retained editorial UX."""

from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from .documents import encode


def enqueue_source(conn, job):
    source = conn.execute("SELECT * FROM media_sources WHERE job_id=%s", (job["id"],)).fetchone()
    batch = uuid5(UUID("c5109880-a9f9-4b3d-9489-a940bec80670"), str(source["id"]))
    body = {
        "project_id": source["project_id"],
        "kind": "ingest",
        "state": "processing",
        "total_items": 1,
        "completed_items": 0,
        "failed_items": 0,
        "failures": [],
        "started_at": datetime.now(UTC),
        "finished_at": None,
        "opened_by": source["created_by"],
        "items": [],
        "stages": {},
    }
    conn.execute(
        "INSERT INTO operational_documents(path,body) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (f"jobs/{batch}", Jsonb(encode(body))),
    )
    attributes = {
        "job_id": str(batch),
        "clip_id": str(source["id"]),
        "project_id": str(source["project_id"]),
        "filename": source["filename"],
        "uploaded_by": source["created_by"],
        "auto_organize": "false",
    }
    conn.execute(
        "INSERT INTO jobs(id,project_id,kind,payload,dedup_key,max_attempts) "
        "VALUES (%s,%s,'editorial_ingest',%s,%s,3) ON CONFLICT DO NOTHING",
        (uuid4(), source["project_id"], Jsonb(attributes), str(batch)),
    )
