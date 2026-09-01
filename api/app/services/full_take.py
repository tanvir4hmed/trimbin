"""Independent full-duration observation of one take.

This is deliberately separate from shot comparison. A clip with no siblings is
still analysed, and a clear measurement margin must not hide an issue at 00:58.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from . import analysis_store, identify, shots, storage
from .ffmpeg_ops import remux

log = logging.getLogger(__name__)

# Both are on the four-second HLS segment grid. A 1:10 take becomes 00:00-01:00
# and 00:52-01:10, so an observation on either side of the join is seen twice
# and can be consolidated with both windows retained as evidence.
WINDOW_SECONDS = 60.0
OVERLAP_SECONDS = 8.0
EMBEDDING_DIMENSIONS = 768


@dataclass(frozen=True, slots=True)
class Window:
    index: int
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


def windows_for(
    duration_s: float,
    *,
    window_s: float = WINDOW_SECONDS,
    overlap_s: float = OVERLAP_SECONDS,
) -> list[Window]:
    """Cover a duration without holes, retaining a bounded overlap."""
    duration = max(0.0, float(duration_s))
    if duration <= 0:
        return []
    if window_s <= 0 or overlap_s < 0 or overlap_s >= window_s:
        raise ValueError("window must be positive and overlap smaller than the window")

    windows: list[Window] = []
    start = 0.0
    step = window_s - overlap_s
    while start < duration:
        end = min(duration, start + window_s)
        windows.append(Window(len(windows), round(start, 3), round(end, 3)))
        if end >= duration:
            break
        start += step
    return windows


def run_key(project_id: int, clip_id: UUID, duration_s: float, prompt_version: str) -> str:
    material = (
        f"{project_id}/{clip_id}/{duration_s:.3f}/{prompt_version}/"
        f"{WINDOW_SECONDS:.1f}/{OVERLAP_SECONDS:.1f}"
    )
    return hashlib.sha256(material.encode()).hexdigest()[:40]


def _value(value: Any) -> str:
    return str(getattr(value, "value", value or ""))


def _absolute_findings(
    observation: Any,
    window: Window,
    segment_id: UUID,
) -> list[dict]:
    found: list[dict] = []
    for finding in observation.findings:
        code = _value(finding.code)
        # A model may describe what happened, but performance preference is a
        # human reason and never a machine finding or ranking signal.
        if code == "performance.note":
            continue

        local_start = max(0.0, min(float(finding.where.start_s), window.duration_s))
        local_end = max(0.0, min(float(finding.where.end_s), window.duration_s))
        if local_end <= local_start:
            local_start, local_end = 0.0, window.duration_s

        found.append(
            {
                "code": code,
                "detail": finding.detail,
                "severity": _value(finding.severity) or "attention",
                "start_s": round(window.start_s + local_start, 3),
                "end_s": round(window.start_s + local_end, 3),
                "evidence_segment_ids": [segment_id],
                "sources": ["observed"],
            }
        )
    return found


_SEVERITY = {"note": 0, "attention": 1, "blocking": 2}


def consolidate_findings(findings: list[dict]) -> list[dict]:
    """Deduplicate overlap observations and keep every evidence segment.

    Only the same taxonomy code with a real time overlap is merged. Two focus
    losses separated by clean footage remain two findings even if their wording
    is similar.
    """
    consolidated: list[dict] = []
    for candidate in sorted(findings, key=lambda f: (f["code"], f["start_s"], f["end_s"])):
        match = next(
            (
                current
                for current in consolidated
                if current["code"] == candidate["code"]
                and min(current["end_s"], candidate["end_s"])
                > max(current["start_s"], candidate["start_s"])
            ),
            None,
        )
        if match is None:
            consolidated.append(
                {
                    **candidate,
                    "evidence_segment_ids": list(candidate["evidence_segment_ids"]),
                    "sources": list(candidate.get("sources", [])),
                }
            )
            continue

        match["start_s"] = min(match["start_s"], candidate["start_s"])
        match["end_s"] = max(match["end_s"], candidate["end_s"])
        if len(candidate.get("detail", "")) > len(match.get("detail", "")):
            match["detail"] = candidate["detail"]
        if _SEVERITY.get(candidate.get("severity", ""), 1) > _SEVERITY.get(
            match.get("severity", ""), 1
        ):
            match["severity"] = candidate["severity"]
        match["evidence_segment_ids"] = list(
            dict.fromkeys([*match["evidence_segment_ids"], *candidate["evidence_segment_ids"]])
        )
        match["sources"] = list(
            dict.fromkeys([*match.get("sources", []), *candidate.get("sources", [])])
        )
    return consolidated


async def analyse_clip(
    *,
    project_id: int,
    clip_id: UUID,
    scene: int,
    shot: int,
    duration_s: float,
    agent: Any | None = None,
) -> dict:
    """Analyse every window, persist only a fully covered current run."""
    from trimbin_agents.config import settings as agent_settings
    from trimbin_agents.segment.agent import PROMPT_VERSION, SegmentAgent

    windows = windows_for(duration_s)
    if not windows:
        raise ValueError("a clip must have positive duration")

    key = run_key(project_id, clip_id, duration_s, PROMPT_VERSION)
    if await analysis_store.already_completed(project_id, key):
        return {"status": "already_analysed", "run_key": key, "windows": len(windows)}

    # Pub/Sub is at-least-once. Stable identities make two delivery attempts
    # converge on the same run, segment, and machine-finding evidence.
    run_id = uuid5(NAMESPACE_URL, f"trimbin/full-take/{key}")
    await analysis_store.record_run(
        run_id=run_id,
        run_key=key,
        project_id=project_id,
        clip_id=clip_id,
        state="started",
        duration_s=duration_s,
        model_id=agent_settings.analyst_model,
        prompt_version=PROMPT_VERSION,
    )

    observer = agent or SegmentAgent()
    shot_meta = await shots.get(project_id, scene, shot)
    briefing = shots.briefing(shot_meta, duration_s)
    segments: list[dict] = []
    candidates: list[dict] = []

    try:
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            for window in windows:
                source = work / f"window-{window.index:04d}.ts"
                if not storage.download_proxy_range(
                    f"p{project_id}/{clip_id}", source, window.start_s, window.end_s
                ):
                    raise RuntimeError(
                        f"proxy window {window.start_s:.2f}-{window.end_s:.2f} is missing"
                    )

                video = await remux(
                    source,
                    work / f"window-{window.index:04d}.mp4",
                    window.duration_s,
                )
                if video is None:
                    raise RuntimeError(
                        f"proxy window {window.start_s:.2f}-{window.end_s:.2f} cannot be read"
                    )

                observation = await observer.run(
                    video.read_bytes(),
                    duration_s=window.duration_s,
                    briefing=briefing,
                )
                segment_id = uuid5(
                    run_id,
                    f"segment/{window.index}/{window.start_s:.3f}/{window.end_s:.3f}",
                )
                searchable = " ".join(
                    [
                        observation.description,
                        observation.transcript,
                        *observation.actions,
                        *observation.objects,
                    ]
                )
                embedding = await identify.embed_text(
                    searchable,
                    subject=f"segment {segment_id}",
                )
                if len(embedding) != EMBEDDING_DIMENSIONS:
                    embedding = [0.0] * EMBEDDING_DIMENSIONS

                segments.append(
                    {
                        "segment_id": segment_id,
                        "run_id": run_id,
                        "project_id": project_id,
                        "clip_id": clip_id,
                        "window_index": window.index,
                        "start_s": window.start_s,
                        "end_s": window.end_s,
                        "description": observation.description,
                        "transcript": observation.transcript,
                        "actions": observation.actions,
                        "objects": observation.objects,
                        "speakers": observation.speakers,
                        "shot_size": observation.shot_size,
                        "camera_motion": observation.camera_motion,
                        "embedding": embedding,
                        "model_id": agent_settings.analyst_model,
                        "prompt_version": PROMPT_VERSION,
                    }
                )
                candidates.extend(_absolute_findings(observation, window, segment_id))
                source.unlink(missing_ok=True)

        for measured in await analysis_store.raw_findings(project_id, clip_id):
            start = max(0.0, min(float(measured["start_s"]), duration_s))
            end = max(0.0, min(float(measured["end_s"]), duration_s))
            if end <= start:
                start, end = 0.0, duration_s
            evidence = [
                segment["segment_id"]
                for segment in segments
                if min(float(segment["end_s"]), end) > max(float(segment["start_s"]), start)
            ]
            candidates.append(
                {
                    **measured,
                    "start_s": start,
                    "end_s": end,
                    "evidence_segment_ids": evidence,
                    "sources": ["measured"],
                }
            )

        consolidated = consolidate_findings(candidates)
        finding_events = []
        for finding in consolidated:
            identity = (
                f"{finding['code']}/{finding['start_s']:.3f}/{finding['end_s']:.3f}/"
                + ",".join(str(s) for s in finding["evidence_segment_ids"])
            )
            finding_id = uuid5(run_id, identity)
            finding_events.append(
                {
                    "event_id": uuid5(finding_id, "revision/0"),
                    "finding_id": finding_id,
                    "run_id": run_id,
                    "project_id": project_id,
                    "clip_id": clip_id,
                    "revision": 0,
                    "action": "machine_open",
                    **finding,
                    "actor_id": "segment-agent",
                    "actor_role": "agent",
                    "model_id": agent_settings.analyst_model,
                    "prompt_version": PROMPT_VERSION,
                }
            )

        await analysis_store.record_segments(segments)
        await analysis_store.record_finding_events(finding_events)
        await analysis_store.record_run(
            run_id=run_id,
            run_key=key,
            project_id=project_id,
            clip_id=clip_id,
            state="completed",
            duration_s=duration_s,
            covered_until_s=windows[-1].end_s,
            window_count=len(windows),
            segment_count=len(segments),
            finding_count=len(finding_events),
            model_id=agent_settings.analyst_model,
            prompt_version=PROMPT_VERSION,
        )
        return {
            "status": "completed",
            "run_id": str(run_id),
            "run_key": key,
            "duration_s": duration_s,
            "covered_until_s": windows[-1].end_s,
            "windows": len(windows),
            "segments": len(segments),
            "findings": len(finding_events),
        }
    except Exception as exc:
        try:
            await analysis_store.record_run(
                run_id=run_id,
                run_key=key,
                project_id=project_id,
                clip_id=clip_id,
                state="failed",
                duration_s=duration_s,
                covered_until_s=segments[-1]["end_s"] if segments else 0.0,
                window_count=len(windows),
                segment_count=len(segments),
                model_id=agent_settings.analyst_model,
                prompt_version=PROMPT_VERSION,
                error=str(exc),
            )
        except Exception:
            log.exception("could not record failed analysis run %s", run_id)
        raise
