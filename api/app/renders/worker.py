"""Bounded original-fed rendering, lossless scratch and single delivery encode."""

import argparse
import asyncio
import os
import shutil
import threading
import time
from fractions import Fraction
from uuid import UUID

from psycopg.types.json import Jsonb

from ..config import Settings
from ..evidence.contracts import EvidenceError
from ..exports.worker import export_root
from ..foundation.jobs import PostgresJobs
from ..inference.contracts import fingerprint
from ..media.files import MediaError, MediaPaths, digest_file, require_space, safe_path
from ..media.processing import probe, run_process
from .plan import VERSION, filters, samples, validated
from .store import RenderStore


async def build(job: dict, config: Settings, lease_check) -> dict:
    started = time.monotonic()
    stopping = threading.Event()

    def check():
        lease_check()
        if stopping.is_set():
            raise EvidenceError("render_interrupted")
        if time.monotonic() - started > config.media_timeout_seconds:
            raise EvidenceError("render_time_limit")

    async def threaded(fn, *args):
        # Cancellation cannot race scratch cleanup against a still-writing thread.
        task = asyncio.create_task(asyncio.to_thread(fn, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            stopping.set()
            await asyncio.gather(task, return_exceptions=True)
            raise

    store = RenderStore(config.database_url)
    payload = job["payload"]
    body = await threaded(
        store.read, job["project_id"], payload["sequence_id"], payload["revision"]
    )
    body = body["body"]
    if payload["version"] != VERSION or fingerprint(body) != payload["snapshot_sha256"]:
        raise EvidenceError("render_snapshot_changed")
    validated(body)
    seq = body["sequence"]
    fps = Fraction(**seq["fps"])
    frame_bytes = seq["width"] * seq["height"] * 3 // 2
    total_samples = sum(samples(c, fps) for c in body["clips"])
    scratch = body["duration_frames"] * frame_bytes + total_samples * 8
    # Raw scratch is intentional: no per-cut lossy encode or mux timestamp rounding.
    # Reserve twice scratch for the current cut and delivery artifact; never lower quality.
    if scratch * 2 > config.media_work_bytes:
        raise EvidenceError("render_scratch_budget_exceeded")
    root = export_root(config)
    relative = f"p{job['project_id']}/{job['id']}/{job['lease_token']}/movie.mp4"
    output = safe_path(root, relative, exists=False)
    output.parent.mkdir(parents=True, exist_ok=False)
    work = output.parent
    paths = MediaPaths(config)
    sources = {}

    def progress(stage, completed=0):
        check()
        with store.connection() as conn:
            row = conn.execute(
                "UPDATE jobs SET result=%s WHERE id=%s AND lease_token=%s "
                "AND state='running' AND NOT cancel_requested "
                "AND lease_until>clock_timestamp() RETURNING id",
                (
                    Jsonb({"stage": stage, "completed": completed, "total": len(body["clips"])}),
                    job["id"],
                    job["lease_token"],
                ),
            ).fetchone()
            if not row:
                raise EvidenceError("render_lease_lost")

    async def run(args):
        await run_process(
            args,
            timeout=config.media_timeout_seconds,
            check=check,
            work=work,
            budget=config.media_work_bytes,
            reserve=config.media_reserve_bytes,
        )

    common = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-n",
        "-threads",
        str(config.media_threads),
        "-filter_complex_threads",
        str(config.media_threads),
    ]
    try:
        require_space(work, scratch * 2, config.media_reserve_bytes)
        encoders = await run_process(
            ["ffmpeg", "-hide_banner", "-encoders"],
            timeout=30,
            check=check,
            capture=True,
        )
        if any(
            name not in encoders.split() for name in (b"libx264", b"aac", b"rawvideo", b"pcm_f32le")
        ):
            raise EvidenceError("render_encoder_unavailable")
        await threaded(progress, "verifying_originals")
        for clip in body["clips"]:
            source_id = clip["source_id"]
            if source_id in sources:
                if sources[source_id][1] != clip["source"]["sha256"]:
                    raise EvidenceError("source_version_changed")
                continue

            def resolve(source_id=source_id, clip=clip):
                with store.connection() as conn:
                    row = store.source(conn, job["project_id"], UUID(source_id))
                path = paths.resolve(job["project_id"], row["root_alias"], row["relative_path"])
                if (
                    row["fingerprint"] != clip["source"]["sha256"]
                    or digest_file(path, check) != row["fingerprint"]
                ):
                    raise EvidenceError("source_version_changed")
                return path, row["fingerprint"]

            path, digest = await threaded(resolve)
            raw = await probe(path, check)
            video = next(s for s in raw["streams"] if s["codec_type"] == "video")
            if (
                video.get("field_order") != "progressive"
                or video.get("sample_aspect_ratio") != "1:1"
                or any(s.get("rotation", 0) != 0 for s in video.get("side_data_list", []))
            ):
                raise EvidenceError("render_requires_progressive_square_unrotated")
            sources[source_id] = (path, digest)
        for index, clip in enumerate(body["clips"]):
            await threaded(progress, "decoding_originals", index)
            vf, af = filters(clip, fps)
            graph = f"[0:v:0]{vf}[v];{af}[a]"
            await run(
                [
                    *common,
                    "-protocol_whitelist",
                    "file,pipe",
                    "-noautorotate",
                    "-i",
                    str(sources[clip["source_id"]][0]),
                    "-filter_complex",
                    graph,
                    "-map",
                    "[v]",
                    "-an",
                    "-c:v",
                    "rawvideo",
                    "-pix_fmt",
                    "yuv420p",
                    "-threads",
                    str(config.media_threads),
                    "-fps_mode",
                    "passthrough",
                    "-f",
                    "rawvideo",
                    str(work / "cut.yuv"),
                    "-map",
                    "[a]",
                    "-vn",
                    "-c:a",
                    "pcm_f32le",
                    "-f",
                    "f32le",
                    str(work / "cut.pcm"),
                ]
            )
            expected = {"yuv": clip["duration_frames"] * frame_bytes, "pcm": samples(clip, fps) * 8}

            def append(expected=expected):
                for ext, size in expected.items():
                    cut = work / f"cut.{ext}"
                    if cut.stat().st_size != size:
                        raise EvidenceError("render_cut_length_mismatch")
                    with cut.open("rb") as src, (work / f"sequence.{ext}").open("ab") as dest:
                        while block := src.read(1024**2):
                            check()
                            require_space(work, len(block), config.media_reserve_bytes)
                            dest.write(block)
                    cut.unlink()

            await threaded(append)
        await threaded(progress, "encoding_delivery", len(body["clips"]))
        await run(
            [
                *common,
                "-f",
                "rawvideo",
                "-pixel_format",
                "yuv420p",
                "-video_size",
                f"{seq['width']}x{seq['height']}",
                "-framerate",
                str(fps),
                "-i",
                str(work / "sequence.yuv"),
                "-f",
                "f32le",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-i",
                str(work / "sequence.pcm"),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-threads",
                str(config.media_threads),
                "-preset",
                "slow",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-color_primaries",
                "bt709",
                "-color_trc",
                "bt709",
                "-colorspace",
                "bt709",
                "-color_range",
                "tv",
                "-c:a",
                "aac",
                "-b:a",
                "320k",
                "-movflags",
                "+faststart",
                "-map_metadata",
                "-1",
                str(output),
            ]
        )
        await threaded(progress, "verifying_output", len(body["clips"]))
        raw = await probe(output, check)
        video = next(s for s in raw["streams"] if s["codec_type"] == "video")
        audio = next(s for s in raw["streams"] if s["codec_type"] == "audio")
        if (
            int(video.get("nb_frames", -1)) != body["duration_frames"]
            or Fraction(video["avg_frame_rate"]) != fps
            or (video["width"], video["height"]) != (seq["width"], seq["height"])
            or audio.get("sample_rate") != "48000"
            or audio.get("channels") != 2
            or abs(Fraction(audio["duration"]) - Fraction(total_samples, 48000))
            > Fraction(1024, 48000)
        ):
            raise EvidenceError("render_output_mismatch")
        for path, digest in sources.values():
            if await threaded(digest_file, path, check) != digest:
                raise EvidenceError("source_version_changed")

        def seal():
            with output.open("rb+") as handle:
                os.fsync(handle.fileno())
            return digest_file(output, check)

        sha = await threaded(seal)
        for ext in ("yuv", "pcm"):
            (work / f"sequence.{ext}").unlink()
        stat = output.stat()
        return {
            "path": relative,
            "sha256": sha,
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "revision": payload["revision"],
            "snapshot_sha256": payload["snapshot_sha256"],
            "format": payload["format"],
            "frames": body["duration_frames"],
            "samples": total_samples,
            "source_sha256": {k: v[1] for k, v in sources.items()},
            "fidelity_acceptance": "pending",
        }
    except BaseException:
        # This attempt directory was created exclusively inside the validated export root.
        shutil.rmtree(work)
        raise


async def process(job: dict, config: Settings):
    queue = PostgresJobs(config.database_url)
    lost = threading.Event()

    def check():
        if lost.is_set():
            raise EvidenceError("render_lease_lost")

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
        result = await build(job, config, check)
        check()
        # The movie is complete before fenced publication. Uncertain DB outcomes retain it.
        await asyncio.to_thread(queue.finish, job["id"], job["lease_token"], result)
    except asyncio.CancelledError:
        lost.set()
        raise
    except Exception as exc:
        code = exc.code if isinstance(exc, (EvidenceError, MediaError)) else "render_job_failed"
        await asyncio.to_thread(queue.fail, job["id"], job["lease_token"], code, False)
    finally:
        pulse.cancel()
        await asyncio.gather(pulse, return_exceptions=True)


async def main(config: Settings, once=False):
    export_root(config)
    queue = PostgresJobs(config.database_url)
    while True:
        job = await asyncio.to_thread(queue.claim, config.job_lease_seconds, ["timeline_render"])
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
