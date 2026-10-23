"""Fenced worker for preserved slate/shot/take editorial operations."""

import asyncio
import logging

from ..config import settings
from ..foundation.jobs import PostgresJobs
from .ingest import handle_analysis_message, handle_message

log = logging.getLogger(__name__)


async def main():
    queue = PostgresJobs(settings.database_url)
    while True:
        job = await asyncio.to_thread(queue.claim, 300, ["editorial_ingest", "editorial_analysis"])
        if not job:
            await asyncio.sleep(2)
            continue
        lost = asyncio.Event()

        async def heartbeat(job=job, lost=lost):
            while True:
                await asyncio.sleep(30)
                if not await asyncio.to_thread(queue.heartbeat, job["id"], job["lease_token"], 300):
                    lost.set()
                    return

        task = asyncio.create_task(heartbeat())
        try:
            handler = (
                handle_analysis_message if job["kind"] == "editorial_analysis" else handle_message
            )
            success = await handler(job["payload"])
            if not success or lost.is_set():
                raise RuntimeError("Editorial job incomplete or lease lost")
            await asyncio.to_thread(queue.finish, job["id"], job["lease_token"], {"complete": True})
        except Exception:
            log.exception("Editorial job %s failed", job["id"])
            await asyncio.to_thread(
                queue.fail, job["id"], job["lease_token"], "editorial_processing_failed"
            )
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
