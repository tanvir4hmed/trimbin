"""Bounded FFmpeg derivatives with explicit source/proxy timestamp mapping."""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

from ..config import Settings
from .files import MediaError, require_space


def rational(value: str | int, *, positive: bool = False) -> dict[str, int]:
    try:
        number = Fraction(str(value))
        if positive and number <= 0:
            raise ValueError
        return {"numerator": number.numerator, "denominator": number.denominator}
    except (ValueError, ZeroDivisionError) as exc:
        raise MediaError("unsupported_media_timing") from exc


def seconds(value: dict) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


async def run_process(
    args: list[str],
    *,
    timeout: int,
    check: Callable[[], None],
    work: Path | None = None,
    budget: int = 0,
    reserve: int = 0,
    capture: bool = False,
) -> bytes:
    if not shutil.which(args[0]):
        raise MediaError("media_tools_missing")
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    async def read_output() -> bytes:
        if proc.stdout is None:
            return b""
        result = bytearray()
        while block := await proc.stdout.read(65536):
            result.extend(block)
            if len(result) > 1024**2:
                raise MediaError("media_metadata_too_large")
        return bytes(result)

    output = asyncio.create_task(read_output())
    started = time.monotonic()
    try:
        while proc.returncode is None:
            check()
            if time.monotonic() - started > timeout:
                raise MediaError("media_processing_timeout")
            if output.done() and output.exception():
                raise output.exception()
            if work:
                used = sum(p.stat().st_size for p in work.rglob("*") if p.is_file())
                if used > budget:
                    raise MediaError("media_work_limit_exceeded")
                require_space(work, 0, reserve)
            await asyncio.sleep(0.2)
        data = await output
        check()
        if proc.returncode:
            raise MediaError("media_decode_failed")
        if work and sum(p.stat().st_size for p in work.rglob("*") if p.is_file()) > budget:
            raise MediaError("media_work_limit_exceeded")
        return data
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        if not output.done():
            output.cancel()
        await asyncio.gather(output, return_exceptions=True)


async def probe(path: Path, check: Callable[[], None] = lambda: None) -> dict:
    payload = await run_process(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_entries",
            "format=duration,start_time,format_name:format_tags=timecode:"
            "stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,"
            "time_base,start_pts,start_time,duration_ts,duration,nb_frames,pix_fmt,"
            "color_space,color_transfer,color_primaries,color_range,sample_aspect_ratio,"
            "sample_rate,channels,channel_layout:stream_tags=timecode:stream_side_data=rotation",
            "-of",
            "json",
            str(path),
        ],
        timeout=60,
        check=check,
        capture=True,
    )
    try:
        return json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise MediaError("invalid_media_metadata") from exc


def source_metadata(raw: dict, size: int) -> dict:
    streams = raw.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None or not video.get("width") or not video.get("height"):
        raise MediaError("video_stream_missing")
    fmt = raw.get("format", {})
    if not set(fmt.get("format_name", "").split(",")) & {"mov", "mp4", "matroska", "avi", "mxf"}:
        raise MediaError("unsupported_media_format")
    duration = video.get("duration") or fmt.get("duration")
    if not duration:
        raise MediaError("unsupported_media_timing")
    return {
        "size_bytes": size,
        "duration": rational(duration, positive=True),
        "frame_rate": rational(video.get("avg_frame_rate", "0/0"), positive=True),
        "nominal_frame_rate": rational(video.get("r_frame_rate", "0/0"), positive=True),
        "time_base": rational(video.get("time_base", "0/0"), positive=True),
        "video_start": rational(video.get("start_time", 0)),
        "timecode": video.get("tags", {}).get("timecode") or fmt.get("tags", {}).get("timecode"),
        "video": video,
        "audio": [s for s in streams if s.get("codec_type") == "audio"],
        "container": fmt.get("format_name"),
    }


async def derivatives(
    source: Path,
    work: Path,
    metadata: dict,
    settings: Settings,
    check: Callable[[], None],
    stage: Callable[[str], None],
) -> dict:
    if metadata["video"].get("color_transfer") in {"smpte2084", "arib-std-b67"}:
        raise MediaError("hdr_proxy_not_supported")
    common = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-n",
        "-protocol_whitelist",
        "file,pipe",
        "-threads",
        str(settings.media_threads),
        "-filter_threads",
        str(settings.media_threads),
    ]
    timeout = settings.media_timeout_seconds
    start = seconds(metadata["video_start"])
    stage("encoding_proxy")
    audio_filter = f"asetpts=PTS-({start.numerator}/{start.denominator})/TB"
    await run_process(
        [
            *common,
            "-copyts",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            "setpts=PTS-STARTPTS,scale=2*trunc(min(1280\\,iw)/2):-2",
            "-af",
            audio_filter,
            "-c:v",
            "libx264",
            "-threads",
            str(settings.media_threads),
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-fps_mode",
            "passthrough",
            "-enc_time_base:v",
            str(seconds(metadata["time_base"])),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-avoid_negative_ts",
            "disabled",
            "-movflags",
            "+faststart",
            str(work / "proxy.mp4"),
        ],
        timeout=timeout,
        check=check,
        work=work,
        budget=settings.media_work_bytes,
        reserve=settings.media_reserve_bytes,
    )
    proxy = source_metadata(
        await probe(work / "proxy.mp4", check), (work / "proxy.mp4").stat().st_size
    )
    tolerance = max(Fraction(1, 20), 2 / seconds(metadata["frame_rate"]))
    if abs(seconds(proxy["duration"]) - seconds(metadata["duration"])) > tolerance:
        raise MediaError("proxy_timing_mismatch")
    if abs(seconds(proxy["video_start"])) > Fraction(1, 1000):
        raise MediaError("proxy_timing_mismatch")
    stage("building_sprite")
    interval = max(Fraction(1, 1), seconds(metadata["duration"]) / 100)
    await run_process(
        [
            *common,
            "-i",
            str(source),
            "-an",
            "-vf",
            f"fps=1/({interval.numerator}/{interval.denominator}),scale=160:-2,tile=10x10",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(work / "sprite.jpg"),
        ],
        timeout=timeout,
        check=check,
        work=work,
        budget=settings.media_work_bytes,
        reserve=settings.media_reserve_bytes,
    )
    result = {
        "proxy": "proxy.mp4",
        "sprite": "sprite.jpg",
        "proxy_metadata": proxy,
        "sprite_interval": rational(str(interval)),
        "sprite_columns": 10,
        "sprite_max_frames": 100,
        "mapping": {
            "source_video_origin": metadata["video_start"],
            "proxy_video_origin": proxy["video_start"],
            "version": 1,
        },
    }
    if metadata["audio"]:
        stage("extracting_audio")
        await run_process(
            [
                *common,
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-c:a",
                "flac",
                "-threads",
                str(settings.media_threads),
                str(work / "audio.flac"),
            ],
            timeout=timeout,
            check=check,
            work=work,
            budget=settings.media_work_bytes,
            reserve=settings.media_reserve_bytes,
        )
        result["audio"] = "audio.flac"
        result["audio_source_origin"] = rational(metadata["audio"][0].get("start_time", 0))
    return result
