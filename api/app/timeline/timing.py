"""Bounded source frame-grid verification, cached by immutable source hash."""

import asyncio
import json
from fractions import Fraction
from itertools import pairwise
from uuid import UUID

from psycopg.types.json import Jsonb

from ..config import Settings
from ..evidence.contracts import EvidenceError
from ..evidence.store import EvidenceStore
from ..media.files import MediaPaths, digest_file
from ..media.processing import run_process, seconds
from .contracts import ratio


def verified_grid(frames: list[dict], metadata: dict) -> dict:
    rate, base = seconds(metadata["frame_rate"]), seconds(metadata["time_base"])
    if base >= 1 / (2 * rate) or rate != seconds(metadata["nominal_frame_rate"]) or not frames:
        raise EvidenceError("variable_rate_conform_unavailable")
    pts = [int(f["best_effort_timestamp"]) for f in frames]
    origin = seconds(metadata["video_start"])
    if abs(pts[0] * base - origin) > base:
        raise EvidenceError("source_origin_mismatch")
    if any(b <= a for a, b in pairwise(pts)) or any(
        abs((value - pts[0]) * base - Fraction(i) / rate) > base for i, value in enumerate(pts)
    ):
        raise EvidenceError("variable_rate_conform_unavailable")
    if abs(Fraction(len(pts)) / rate - seconds(metadata["duration"])) > 1 / rate:
        raise EvidenceError("source_duration_mismatch")
    video = metadata["video"]
    if video.get("color_transfer") in {"smpte2084", "arib-std-b67"}:
        raise EvidenceError("hdr_timeline_unavailable")
    audio = metadata["audio"][0] if metadata["audio"] else None
    if audio and not all(k in audio for k in ("start_time", "index", "channels", "sample_rate")):
        raise EvidenceError("audio_timing_unavailable")
    return {
        "fps": ratio(rate),
        "frame_count": len(pts),
        "time_base": ratio(base),
        "video_start": ratio(origin),
        "timecode": metadata.get("timecode"),
        "width": video["width"],
        "height": video["height"],
        "audio": None
        if audio is None
        else {
            "stream_index": audio["index"],
            "channels": audio.get("channels"),
            "sample_rate": audio.get("sample_rate"),
            "offset_seconds": ratio(Fraction(str(audio.get("start_time", 0))) - origin),
        },
        "grid": "verified-cfr-v1",
        "color": {
            k: video.get(k)
            for k in ("color_space", "color_transfer", "color_primaries", "color_range", "pix_fmt")
        },
    }


async def prepare(config: Settings, project: int, source_id: UUID, actor: str) -> dict:
    store = EvidenceStore(config.database_url)
    with store.connection() as conn:
        store.authorize_writer(conn, project, actor)
        row = store.source(conn, project, source_id)
    paths = MediaPaths(config)
    path = paths.resolve(project, row["root_alias"], row["relative_path"])
    if await asyncio.to_thread(digest_file, path) != row["fingerprint"]:
        raise EvidenceError("source_version_changed")
    key = f"{source_id}/{row['fingerprint']}"
    with store.connection() as conn:
        cached = conn.execute(
            "SELECT body FROM state_documents WHERE project_id=%s "
            "AND kind='source_timing' AND document_id=%s",
            (project, key),
        ).fetchone()
    if cached:
        return cached["body"]
    raw = await run_process(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-select_streams",
            "v:0",
            "-show_frames",
            "-show_entries",
            "frame=best_effort_timestamp",
            "-of",
            "json",
            str(path),
        ],
        timeout=config.media_timeout_seconds,
        check=lambda: None,
        capture=True,
    )
    result = verified_grid(json.loads(raw)["frames"], row["metadata"])
    if await asyncio.to_thread(digest_file, path) != row["fingerprint"]:
        raise EvidenceError("source_version_changed")
    result.update(
        {"source_id": str(source_id), "sha256": row["fingerprint"], "filename": row["filename"]}
    )
    with store.connection() as conn:
        store.authorize_writer(conn, project, actor)
        conn.execute(
            "INSERT INTO state_documents(project_id,kind,document_id,body) "
            "VALUES (%s,'source_timing',%s,%s) ON CONFLICT DO NOTHING",
            (project, key, Jsonb(result)),
        )
    return result
