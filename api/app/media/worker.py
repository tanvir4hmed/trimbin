"""Run with python -m app.media.worker; one bounded media job per process."""

from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
import threading
from uuid import UUID

from ..config import Settings, settings
from ..foundation.jobs import PostgresJobs
from .files import MediaError, MediaPaths, digest_file, file_signature, require_space, safe_path
from .processing import derivatives, probe, source_metadata
from .store import MediaStore

log = logging.getLogger(__name__)


async def process_job(job: dict, store: MediaStore, queue: PostgresJobs, config: Settings) -> None:
    paths = MediaPaths(config)
    lost = threading.Event()

    def check() -> None:
        if lost.is_set():
            raise MediaError("lease_lost")

    async def heartbeat() -> None:
        try:
            while True:
                await asyncio.sleep(config.job_lease_seconds / 3)
                owned = await asyncio.to_thread(
                    queue.heartbeat,
                    job["id"],
                    job["lease_token"],
                    config.job_lease_seconds,
                )
                if not owned:
                    lost.set()
                    return
        except Exception:
            lost.set()

    task = asyncio.create_task(heartbeat())
    # Each attempt owns its own folder. Stale workers cannot overwrite new output.
    relative_work = f"p{job['project_id']}/{UUID(job['payload']['source_id'])}/{job['lease_token']}"
    work = safe_path(paths.derivatives, relative_work, exists=False)
    published = False
    publication_attempted = False
    try:
        work.mkdir(parents=True, exist_ok=False)
        require_space(work, config.media_work_bytes, config.media_reserve_bytes)
        source = await asyncio.to_thread(
            store.get, job["project_id"], UUID(job["payload"]["source_id"])
        )
        path = paths.resolve(job["project_id"], source["root_alias"], source["relative_path"])
        original_signature = file_signature(path)
        await asyncio.to_thread(store.stage, job, "hashing_source")
        fingerprint = await asyncio.to_thread(digest_file, path, check)
        metadata = source_metadata(await probe(path, check), original_signature[2])
        result = await derivatives(
            path, work, metadata, config, check, lambda s: store.stage(job, s)
        )
        await asyncio.to_thread(store.stage, job, "verifying_source")
        if original_signature != file_signature(path) or fingerprint != await asyncio.to_thread(
            digest_file,
            path,
            check,
        ):
            raise MediaError("source_changed")
        # Re-resolve the configured root to detect a replaced path before publishing.
        if paths.resolve(job["project_id"], source["root_alias"], source["relative_path"]) != path:
            raise MediaError("source_changed")
        result["directory"] = relative_work
        publication_attempted = True
        await asyncio.to_thread(store.publish, job, fingerprint, metadata, result)
        published = True
    except asyncio.CancelledError:
        lost.set()
        raise
    except Exception as exc:
        code = (
            exc.code
            if isinstance(exc, MediaError)
            else ("source_missing" if isinstance(exc, FileNotFoundError) else "media_job_failed")
        )
        log.warning("media job %s: %s", job["id"], code)
        await asyncio.to_thread(
            queue.fail,
            job["id"],
            job["lease_token"],
            code,
            retry=code in {"media_processing_timeout", "media_job_failed"},
        )
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if not published and not publication_attempted and work.exists():
            # Only this attempt's validated UUID directory is owned by this process.
            shutil.rmtree(work)


async def main(config: Settings = settings, once: bool = False) -> None:
    MediaPaths(config)
    store, queue = MediaStore(config.database_url), PostgresJobs(config.database_url)
    while True:
        job = await asyncio.to_thread(queue.claim, config.job_lease_seconds, ["media_index"])
        if job:
            await process_job(job, store, queue, config)
        else:
            if once:
                return
            await asyncio.sleep(2)
        if once:
            return


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(Settings(_env_file=args.env_file), args.once))
