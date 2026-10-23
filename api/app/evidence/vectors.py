"""Durable, bounded automatic indexing of the latest human-reviewed workspace."""

import asyncio

from ..config import settings
from ..foundation.jobs import PostgresJobs
from ..inference.provider import InferenceError
from .contracts import EvidenceError
from .projection import build_vectors, eligible
from .store import EvidenceStore


async def main():
    queue = PostgresJobs(settings.database_url)
    while True:
        job = await asyncio.to_thread(queue.claim, 300, ["evidence_vectors"])
        if not job:
            await asyncio.sleep(2)
            continue

        async def heartbeat(job=job):
            while True:
                await asyncio.sleep(60)
                if not await asyncio.to_thread(queue.heartbeat, job["id"], job["lease_token"], 300):
                    return

        pulse = asyncio.create_task(heartbeat())
        try:
            snapshot = await asyncio.to_thread(
                EvidenceStore(settings.database_url).snapshot, job["project_id"]
            )
            if snapshot["revision"] != job["payload"]["revision"] or not eligible(snapshot):
                result = {"superseded_or_empty": True}
            else:
                result = await build_vectors(settings, job["project_id"])
            await asyncio.to_thread(queue.finish, job["id"], job["lease_token"], result)
        except Exception as exc:
            code = (
                exc.code
                if isinstance(exc, (EvidenceError, InferenceError))
                else "vector_index_failed"
            )
            await asyncio.to_thread(queue.fail, job["id"], job["lease_token"], code)
        finally:
            pulse.cancel()
            await asyncio.gather(pulse, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
