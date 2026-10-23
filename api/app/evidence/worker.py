"""Bounded original-frame preparation and complete-run evidence publication."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
import shutil
import threading
import time
from fractions import Fraction
from pathlib import Path
from uuid import UUID

from psycopg.types.json import Jsonb

from ..config import Settings
from ..foundation.jobs import PostgresJobs
from ..inference.cli import verify_registered_sources
from ..inference.contracts import TaskRequest, fingerprint
from ..inference.provider import InferenceError, load_catalog
from ..inference.runner import run_task
from ..media.files import MediaPaths, require_space, safe_path
from ..media.store import MediaStore
from .contracts import EvidenceError
from .store import EvidenceStore


def configuration_identity(config: Settings) -> dict:
    # No keys, DSNs or secrets in durable manifests.
    profile_hash = None
    if config.inference_mode == "nebius":
        profiles = load_catalog(config.inference_catalog_path)
        profile_hash = fingerprint({k: v.model_dump() for k, v in profiles.items()})
    return {
        "mode": config.inference_mode,
        "vision": config.vision_model,
        "reasoning": config.reasoning_model,
        "catalog_hash": profile_hash,
        "temperature": config.inference_temperature,
        "max_tokens": config.inference_max_output_tokens,
        "frame_recipe": "original-png-pts-v1",
        "adapter": "tokenfactory-v1",
    }


def windows(duration: int, length: int, overlap: int) -> list[tuple[int, int]]:
    if overlap >= length:
        raise EvidenceError("overlap_must_be_smaller_than_window")
    result, start = [], 0
    while start < duration:
        end = min(duration, start + length)
        result.append((start, end))
        if len(result) > 256:
            raise EvidenceError("analysis_window_limit")
        if end == duration:
            break
        start = end - overlap
    return result


async def extract_frame(source: Path, output: Path, absolute: Fraction, config: Settings, check):
    """Decode from the original and retain actual PTS, not an average-FPS guess."""
    if not shutil.which("ffmpeg"):
        raise EvidenceError("media_tools_missing")
    args = [
        "ffmpeg",
        "-nostdin",
        "-n",
        "-v",
        "info",
        "-protocol_whitelist",
        "file,pipe",
        "-threads",
        str(config.media_threads),
        "-filter_threads",
        str(config.media_threads),
        "-copyts",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        f"select=gte(t\\,{absolute.numerator}/{absolute.denominator}),showinfo",
        "-frames:v",
        "1",
        "-fps_mode",
        "passthrough",
        "-threads",
        str(config.media_threads),
        str(output),
    ]
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    async def consume():
        data = bytearray()
        while block := await process.stderr.read(65536):
            data.extend(block)
            if len(data) > 1024**2:
                raise EvidenceError("frame_diagnostics_limit")
        return data.decode("utf-8", errors="replace")

    reader = asyncio.create_task(consume())
    started = time.monotonic()
    try:
        while process.returncode is None:
            check()
            require_space(output.parent, 0, config.media_reserve_bytes)
            if output.exists() and output.stat().st_size > 32 * 1024**2:
                raise EvidenceError("frame_size_limit")
            if time.monotonic() - started > config.media_timeout_seconds:
                raise EvidenceError("frame_extraction_timeout")
            if reader.done() and reader.exception():
                raise reader.exception()
            await asyncio.sleep(0.2)
        diagnostic = await reader
        check()
        pts = re.search(r"\bn:\s*0\s+pts:\s*(-?\d+)", diagnostic)
        base = re.search(r"config in time_base:\s*(\d+)/(\d+)", diagnostic)
        if process.returncode or not pts or not base or not output.is_file():
            raise EvidenceError("frame_extraction_failed")
        if output.stat().st_size > 32 * 1024**2:
            raise EvidenceError("frame_size_limit")
        return Fraction(int(pts[1]) * int(base[1]), int(base[2]))
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
        if not reader.done():
            reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)


def review_request(plan: dict) -> TaskRequest:
    candidates, evidence = [], []
    for item in plan["selections"]:
        span = {k: item[k] for k in ("source_id", "start_us", "end_us")}
        candidates.append({**span, "id": item["selection_id"]})
        evidence.append(
            {**span, "id": "e-" + item["selection_id"], "text": item["text"], "modality": "editor"}
        )
    return TaskRequest.model_validate(
        {
            "project_id": plan["project_id"],
            "task": plan["task"],
            "sources": plan["sources"],
            "windows": candidates,
            "candidates": candidates,
            "evidence": evidence,
            "brief": plan["brief"],
            "brief_revision": plan["command_id"],
            "evidence_revision": str(plan["evidence_revision"]),
            "recipe": "selected-evidence-v1",
        }
    )


async def process(job: dict, config: Settings) -> None:
    store, queue = EvidenceStore(config.database_url), PostgresJobs(config.database_url)
    run = await asyncio.to_thread(store.run, job["project_id"], UUID(job["payload"]["run_id"]))
    plan, records = run["plan"], []
    lost = threading.Event()
    work = None

    def check():
        if lost.is_set():
            raise EvidenceError("lease_lost")

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
        if plan["config"] != configuration_identity(config):
            raise EvidenceError("analysis_configuration_changed")
        if run["mode"] != config.inference_mode:
            raise EvidenceError("analysis_mode_mismatch")
        catalog = load_catalog(config.inference_catalog_path) if run["mode"] == "nebius" else {}

        async def execute(request, assets):
            check()
            fixture = None
            if run["mode"] == "fixture":
                fixture = {
                    "input_fingerprint": fingerprint(request.model_dump(mode="json")),
                    "output": {
                        "status": "abstained",
                        "reason": "Development fixture: no model analysis performed.",
                        "findings": [],
                        "ranking": [],
                        "draft": [],
                    },
                }
            record = await run_task(request, assets, config, catalog, fixture=fixture, check=check)
            records.append(record)
            check()
            if record["status"] not in {"fixture", "validated"}:
                raise EvidenceError(record.get("error_code") or "analysis_failed")

        if run["task"] in {"comparison", "continuity"}:
            request = review_request(plan)
            await asyncio.to_thread(verify_registered_sources, request, config)
            await execute(request, {})
            await asyncio.to_thread(verify_registered_sources, request, config)
        else:
            paths = MediaPaths(config)
            relative = f"analysis/{run['id']}/{job['lease_token']}"
            work = safe_path(paths.derivatives, relative, exists=False)
            work.mkdir(parents=True, exist_ok=False)
            source = await asyncio.to_thread(
                MediaStore(config.database_url).get, job["project_id"], UUID(plan["source_id"])
            )
            if source["metadata"]["video"].get("color_transfer") in {"smpte2084", "arib-std-b67"}:
                raise EvidenceError("hdr_analysis_recipe_unverified")
            original = paths.resolve(
                job["project_id"], source["root_alias"], source["relative_path"]
            )
            origin = source["metadata"]["video_start"]
            origin = Fraction(origin["numerator"], origin["denominator"])
            interval = plan["sample_every_seconds"] * 1000000
            frame_limit = catalog[config.vision_model].max_frames if catalog else 8
            length = min(plan["window_seconds"] * 1000000, frame_limit * interval)
            overlap = min(plan["overlap_seconds"] * 1000000, max(0, length - interval))
            spans = windows(plan["sources"][0]["duration_us"], length, overlap)
            total_frames = 0
            for index, (start, end) in enumerate(spans):
                frames, assets = [], {}
                for sample in range(start, end, plan["sample_every_seconds"] * 1000000):
                    total_frames += 1
                    if total_frames > 4096:
                        raise EvidenceError("analysis_frame_limit")
                    output = work / f"frame-{index}-{sample}.png"
                    actual = await extract_frame(
                        original, output, origin + Fraction(sample, 1000000), config, check
                    )
                    at = round((actual - origin) * 1000000)
                    if not start <= at < end:
                        raise EvidenceError("frame_outside_analysis_window")
                    data = output.read_bytes()
                    frame_id = f"w{index}-t{at}"
                    frames.append(
                        {
                            "id": frame_id,
                            "source_id": plan["source_id"],
                            "at_us": at,
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "mime": "image/png",
                        }
                    )
                    assets[frame_id] = data
                    output.unlink()  # Own derivative only; the original is read-only.
                    if sum(len(v) for v in assets.values()) > 128 * 1024**2:
                        raise EvidenceError("analysis_window_bytes_limit")
                request = TaskRequest.model_validate(
                    {
                        "project_id": job["project_id"],
                        "task": run["task"],
                        "sources": plan["sources"],
                        "windows": [
                            {
                                "id": f"w{index}",
                                "source_id": plan["source_id"],
                                "start_us": start,
                                "end_us": end,
                            }
                        ],
                        "frames": frames,
                        "brief_revision": plan["command_id"],
                        "evidence_revision": str(plan["evidence_revision"]),
                        "recipe": (
                            f"original-png-pts-v1; every={plan['sample_every_seconds']}s; "
                            f"window={index}/{len(spans)}; sparse coverage is not exhaustive"
                        ),
                        "allowed_labels": plan["allowed_labels"],
                    }
                )
                if index == 0:
                    await asyncio.to_thread(verify_registered_sources, request, config)
                await execute(request, assets)
            await asyncio.to_thread(verify_registered_sources, request, config)
        check()
        await asyncio.to_thread(store.publish, job, run, records)
    except asyncio.CancelledError:
        lost.set()
        raise
    except Exception as exc:
        code = exc.code if isinstance(exc, (EvidenceError, InferenceError)) else "analysis_failed"
        with store.connection() as conn:
            if MediaStore.owned(conn, job):
                conn.execute(
                    "UPDATE evidence_runs SET result=%s WHERE id=%s",
                    (Jsonb({"records": records, "error_code": code}), run["id"]),
                )
        await asyncio.to_thread(queue.fail, job["id"], job["lease_token"], code, False)
    finally:
        pulse.cancel()
        await asyncio.gather(pulse, return_exceptions=True)
        if work and work.exists():
            shutil.rmtree(work)


async def main(config: Settings, once: bool = False):
    queue = PostgresJobs(config.database_url)
    while True:
        job = await asyncio.to_thread(queue.claim, config.job_lease_seconds, ["evidence_analysis"])
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
