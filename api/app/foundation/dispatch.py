"""Durable editorial dispatch over the same PostgreSQL job queue."""

import json
from concurrent.futures import Future
from uuid import uuid4

from .jobs import PostgresJobs


class DurablePublisher:
    def topic_path(self, project, topic):
        return "trimbin-editorial"

    def publish(self, topic, data, **attributes):
        from ..config import settings

        future = Future()
        try:
            payload = attributes or json.loads(data)
            kind = (
                "editorial_analysis"
                if payload.get("task") == "full_take_analysis"
                else "editorial_ingest"
            )
            identity = (
                payload.get("dispatch_id")
                or f"{payload.get('job_id')}/{payload.get('clip_id')}/{uuid4()}"
            )
            job = PostgresJobs(settings.database_url).enqueue(
                int(payload["project_id"]), kind, payload, identity
            )
            future.set_result(str(job))
        except Exception as exc:
            future.set_exception(exc)
        return future
