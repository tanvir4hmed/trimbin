"""Durable editable-export worker; reads originals and writes its own bounded ZIP."""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import threading
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from ..config import Settings
from ..evidence.contracts import EvidenceError
from ..foundation.jobs import PostgresJobs
from ..inference.contracts import fingerprint
from ..media.files import MediaError, MediaPaths, digest_file, require_space, safe_path
from .formats import VERSION, fcp7, manifest
from .store import ExportStore

LIMIT = 32 * 1024**2


def export_root(config: Settings) -> Path:
    if not config.export_root:
        raise EvidenceError("exports_not_configured")
    MediaPaths(config)  # Enforce separation from originals, staging and proxy roots.
    root = Path(config.export_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def build(job: dict, config: Settings, check) -> dict:
    payload = job["payload"]
    if payload["version"] != VERSION:
        raise EvidenceError("export_version_changed")
    store = ExportStore(config.database_url)
    body = store.read(job["project_id"], payload["sequence_id"], payload["revision"])["body"]
    if fingerprint(body) != payload["snapshot_sha256"]:
        raise EvidenceError("export_snapshot_changed")
    paths = MediaPaths(config)
    media = {}
    for clip in body["clips"]:
        check()
        source_id = clip["source_id"]
        if source_id in media:
            if media[source_id]["sha256"] != clip["source"]["sha256"]:
                raise EvidenceError("source_version_changed")
            continue
        with store.connection() as conn:
            source = store.source(conn, job["project_id"], UUID(source_id))
        if source["fingerprint"] != clip["source"]["sha256"]:
            raise EvidenceError("source_version_changed")
        path = paths.resolve(job["project_id"], source["root_alias"], source["relative_path"])
        if digest_file(path, check) != source["fingerprint"]:
            raise EvidenceError("source_version_changed")
        media[source_id] = {
            "root_alias": source["root_alias"],
            "relative_path": source["relative_path"],
            "sha256": source["fingerprint"],
            "filename": source["filename"],
            "video": source["metadata"]["video"],
            "audio_streams": len(source["metadata"]["audio"]),
        }
    document = manifest(job["project_id"], payload["sequence_id"], payload["revision"], body, media)
    files = {
        "timeline.json": json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8"),
        "roots.example.json": json.dumps(
            dict.fromkeys({m["root_alias"] for m in media.values()}, ""), indent=2
        ).encode(),
        "README.txt": b"Original footage is not included. timeline.json is the saved snapshot.\n"
        b"XML uses placeholder paths. Map aliases in roots.json, then run:\n"
        b"python relink.py --roots roots.json (Python 3.11+).\n"
        b"Local originals are hashed; timeline-relinked.xml is created.\n"
        b"Keep subdirectories under each root. Originals are never changed.\n"
        b"Import into Premiere; verify cuts, timecodes, links and audio sync.\n"
        b"Premiere import is unverified. XML blocks mixed rates and nonzero\n"
        b"audio offsets; native export retains them. No cloud path is included.\n",
    }
    if payload["format"] == "fcp7":
        files["timeline.xml"] = fcp7(body, media, payload["sequence_id"], payload["revision"])
        files["relink.py"] = Path(__file__).with_name("relink.py").read_bytes()
    if sum(map(len, files.values())) > LIMIT:
        raise EvidenceError("export_size_limit")
    files["checksums.json"] = json.dumps(
        {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}, indent=2
    ).encode()
    root = export_root(config)
    relative = f"p{job['project_id']}/{job['id']}/{job['lease_token']}/timeline.zip"
    output = safe_path(root, relative, exists=False)
    output.parent.mkdir(parents=True, exist_ok=False)
    require_space(output.parent, LIMIT, config.media_reserve_bytes)
    try:
        with output.open("xb") as handle:
            with ZipFile(handle, "w", ZIP_DEFLATED) as archive:
                for name, data in files.items():
                    check()
                    archive.writestr(name, data)
            handle.flush()
            os.fsync(handle.fileno())
        check()
        if output.stat().st_size > LIMIT:
            raise EvidenceError("export_size_limit")
        return {
            "path": relative,
            "sha256": digest_file(output, check),
            "bytes": output.stat().st_size,
            "revision": payload["revision"],
            "format": payload["format"],
            "snapshot_sha256": payload["snapshot_sha256"],
            "premiere_import_verified": False,
        }
    except BaseException:
        # Only this attempt's directory, already resolved under the configured export root.
        shutil.rmtree(output.parent)
        raise


async def process(job: dict, config: Settings):
    queue = PostgresJobs(config.database_url)
    lost = threading.Event()

    def check():
        if lost.is_set():
            raise EvidenceError("export_lease_lost")

    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(config.job_lease_seconds / 3)
                if not await asyncio.to_thread(
                    queue.heartbeat, job["id"], job["lease_token"], config.job_lease_seconds
                ):
                    lost.set()
                    return
        except Exception:
            lost.set()

    pulse = asyncio.create_task(heartbeat())
    try:
        result = await asyncio.to_thread(build, job, config, check)
        check()
        # The ZIP is complete before fenced publication. Uncertain DB outcomes retain it.
        await asyncio.to_thread(queue.finish, job["id"], job["lease_token"], result)
    except asyncio.CancelledError:
        lost.set()
        raise
    except Exception as exc:
        code = exc.code if isinstance(exc, (EvidenceError, MediaError)) else "export_job_failed"
        await asyncio.to_thread(queue.fail, job["id"], job["lease_token"], code, False)
    finally:
        pulse.cancel()
        await asyncio.gather(pulse, return_exceptions=True)


async def main(config: Settings, once=False):
    export_root(config)
    queue = PostgresJobs(config.database_url)
    while True:
        job = await asyncio.to_thread(queue.claim, config.job_lease_seconds, ["timeline_export"])
        if job:
            await process(job, config)
        if once:
            return
        if not job:
            await asyncio.sleep(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(Settings(_env_file=args.env_file), args.once))
