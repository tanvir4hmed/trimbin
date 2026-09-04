"""Judging one setup: read the takes, convene the panel, record the verdicts.

This is the seam between the archive and the agents. Everything above it works
in ClickHouse rows; everything below it works in contracts. Keeping the join in
one place means the Analyst never learns what a database looks like, and the
schema never learns what a prompt looks like.

Run per setup, not per scene. A wide and a close-up of the same moment are not
alternatives to each other — choosing between them is a story question, and the
system has no standing to answer it. Only takes of the same camera position are
comparable at all, and comparing across setups would produce a confident answer
to a question nobody asked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from . import analysis_store, assessment, criteria, storage
from . import decisions as decisions_service
from . import ranges as ranges_service
from . import shots as shots_service
from .analytics import client
from .ffmpeg_ops import remux

log = logging.getLogger(__name__)

# How much comparative footage the continuity panel previews together.
#
# This is not the take-analysis coverage limit. Every clip has already been
# observed independently over overlapping full-duration windows and those
# findings are supplied to the chief. The preview exists only for direct
# cross-take comparison; a 00:58 issue is still present in the full-take report.
PANEL_WINDOW_S = 30.0

# Below this many takes there is nothing to compare.
MIN_TAKES = 2


@dataclass(slots=True)
class Setup:
    project_id: int
    group_id: int
    subgroup_id: int
    clip_ids: list[UUID]


class NotReady(Exception):
    """The setup cannot be judged yet, and saying why is the useful part."""


async def pending(project_id: int) -> list[Setup]:
    """Setups with takes and no verdict.

    Deliberately not "setups with new takes since the last verdict". Re-judging
    on every arrival would spend the panel's cost repeatedly on a setup that is
    still being uploaded, and the answer from three takes is not worth paying for
    when seven are coming.
    """
    ch = await client()
    result = await ch.query(
        """
        SELECT c.group_id, c.subgroup_id, groupArray(c.clip_id) AS clip_ids
        FROM current_clip_placement AS c
        WHERE c.project_id = {p:UInt32} AND c.status = 'active'
        GROUP BY c.group_id, c.subgroup_id
        HAVING count() >= {min:UInt8}
           AND (
                SELECT count()
                FROM decisions AS d
                WHERE d.project_id = {p:UInt32}
                  AND d.group_id = c.group_id
                  AND d.subgroup_id = c.subgroup_id
           ) = 0
        ORDER BY c.group_id, c.subgroup_id
        """,
        parameters={"p": project_id, "min": MIN_TAKES},
    )
    return [
        Setup(project_id, int(g), int(s), [UUID(str(c)) for c in ids])
        for g, s, ids in result.result_rows
    ]


async def judge(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    force: bool = False,
) -> dict:
    """Compare every take of one setup and record what was decided.

    Relative measurements are derived in memory from the takes that exist now.
    Interactive review must never launch a ClickHouse mutation.
    """
    takes = await _load(project_id, group_id, subgroup_id)
    normalised = len(takes) if len(takes) >= 2 else 0

    if len(takes) < MIN_TAKES:
        raise NotReady(
            f"scene {group_id} shot {subgroup_id} has {len(takes)} take(s); "
            "there is nothing to compare"
        )

    incomplete = [take for take in takes if take.get("analysis_complete") is False]
    if incomplete:
        raise NotReady(
            f"full-take analysis is still pending for {len(incomplete)} of "
            f"{len(takes)} take(s); no recommendation was recorded"
        )

    key = decisions_service.run_hash(
        project_id, group_id, subgroup_id, [t["clip_id"] for t in takes]
    )
    if not force and await decisions_service.already_recorded(project_id, key):
        log.info("scene %d setup %d already judged for this take set", group_id, subgroup_id)
        return {"status": "already_judged", "run_hash": key, "takes": len(takes)}

    # Imported here rather than at module scope so that importing this service
    # does not require the agents package — the API container has it, but the
    # tests for everything around this should not need a model SDK installed to
    # run.
    from trimbin_agents.analyst.agent import PROMPT_VERSION, AnalystAgent
    from trimbin_agents.config import settings as agent_settings
    from trimbin_agents.contracts.analysis import AnalysisRequest, Measurements
    from trimbin_agents.contracts.base import ClipRef, Finding, TimeRange

    shot_meta = await shots_service.get(project_id, group_id, subgroup_id)

    request = AnalysisRequest(
        clips=[
            ClipRef(
                clip_id=t["clip_id"],
                project_id=project_id,
                group_id=group_id,
                subgroup_id=subgroup_id,
                take_no=t["take_no"],
            )
            for t in takes
        ],
        # What the production said this shot was for, if anything. Empty is the
        # normal case and costs nothing; where it exists it turns "different
        # from the others" into "different from what was planned", which is the
        # only way to catch a shot where every take drifted together.
        briefing=shots_service.briefing(shot_meta),
        measurements={
            t["clip_id"]: Measurements(
                exposure_rel=t["exposure_rel"],
                clipping_pct=t["clipping_pct"],
                sharpness_rel=t["sharpness_rel"],
                motion_rel=t["motion_rel"],
                audio_lufs=t["audio_lufs"],
                noise_floor_db=t["noise_floor_db"],
                duration_s=t["duration_s"],
                dropped_frames=t["dropped_frames"],
            )
            for t in takes
        },
        observed_findings={
            t["clip_id"]: [
                Finding(
                    code=f["code"],
                    detail=f.get("detail", "")[:200],
                    severity=f.get("severity") or "attention",
                    where=TimeRange(start_s=f["start_s"], end_s=f["end_s"]),
                )
                for f in t.get("findings", [])
                if f.get("code") != "performance.note"
            ]
            for t in takes
        },
    )

    # Video is fetched only if the panel will actually sit. The fast path
    # decides on measurements alone, and downloading seven takes to not look at
    # them is the most expensive way to reach the same answer.
    agent = AnalystAgent()
    with TemporaryDirectory() as tmp:
        clip_bytes = {}
        if _panel_likely(request):
            clip_bytes = await _fetch_windows(project_id, takes, Path(tmp))

        result = await agent.run(request, clip_bytes)
        panel_convened = bool(clip_bytes)

    written = await decisions_service.record(
        project_id=project_id,
        group_id=group_id,
        subgroup_id=subgroup_id,
        verdicts=_as_rows(result, takes),
        key=key,
        model_id=agent_settings.analyst_model,
        prompt_version=PROMPT_VERSION,
        panel_convened=panel_convened,
    )

    log.info(
        "judged scene %d setup %d: %d takes, winner %s, margin %.2f",
        group_id,
        subgroup_id,
        len(takes),
        result.winner_id,
        result.margin,
    )

    return {
        "status": "judged",
        "run_hash": key,
        "takes": len(takes),
        "normalised": normalised,
        "winner": str(result.winner_id) if result.winner_id else None,
        "margin": round(result.margin, 4),
        "panel_convened": panel_convened,
        "needs_review": result.margin < assessment.review_margin(),
        "rationale": result.rationale,
        "verdicts_written": written,
    }


def _panel_likely(request) -> bool:
    """Would the panel sit, on these measurements alone?

    Asked before fetching video, because fetching is the part that costs. The
    Analyst makes the real decision; this only has to be right about when video
    will be needed, and it errs towards fetching — a panel with no footage would
    have to fall back, and the fallback is the answer we were trying to improve
    on.
    """
    from trimbin_agents.analyst.agent import _rank_on_measurements
    from trimbin_agents.config import settings as agent_settings

    _, margin = _rank_on_measurements(request)
    return bool(any(request.observed_findings.values())) or margin < agent_settings.panel_margin


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _ratio(value: float, median: float) -> float:
    return round(value / median, 4) if value > 0 and median > 0 else 1.0


async def _load(project_id: int, group_id: int, subgroup_id: int) -> list[dict]:
    ch = await client()
    result = await ch.query(
        """
        SELECT clip_id, take_no, storage_uri, duration_ms,
               exposure_rel, clipping_pct, sharpness_rel, motion_rel,
               audio_lufs, noise_floor_db, dropped_frames, normalised_at,
               finding_codes, finding_starts_s, finding_ends_s,
               exposure_raw, sharpness_raw, motion_raw
        FROM current_clip_placement
        WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
          AND subgroup_id = {s:UInt32} AND status = 'active'
        ORDER BY take_no, clip_id
        """,
        parameters={"p": project_id, "g": group_id, "s": subgroup_id},
    )

    takes = []
    raw_rows = list(result.result_rows)
    exposure_median = _median([float(row[15]) for row in raw_rows]) if raw_rows else 0.0
    sharpness_median = _median([float(row[16]) for row in raw_rows]) if raw_rows else 0.0
    motion_median = _median([float(row[17]) for row in raw_rows]) if raw_rows else 0.0
    for row in raw_rows:
        takes.append(
            {
                "clip_id": UUID(str(row[0])),
                "take_no": int(row[1]),
                "storage_uri": str(row[2]),
                "duration_s": max(int(row[3]) / 1000, 0.001),
                "exposure_rel": _ratio(float(row[15]), exposure_median),
                "clipping_pct": min(max(float(row[5]), 0.0), 100.0),
                "sharpness_rel": _ratio(float(row[16]), sharpness_median),
                "motion_rel": _ratio(float(row[17]), motion_median),
                "audio_lufs": float(row[8]),
                "noise_floor_db": float(row[9]),
                "dropped_frames": int(row[10]),
                # What ffmpeg found at ingest. These exist before any judgement and
                # are the evidence the panel is handed, rather than something it is
                # asked to notice for itself.
                "findings": [
                    {
                        "code": str(code),
                        "start_s": float(start),
                        "end_s": float(end),
                        "severity": "attention",
                        "detail": "",
                    }
                    for code, start, end in zip(row[12], row[13], row[14], strict=True)
                ],
            }
        )
    complete, findings = await analysis_store.working_findings_for_clips(
        project_id,
        [take["clip_id"] for take in takes],
    )
    for take in takes:
        take["analysis_complete"] = str(take["clip_id"]) in complete
        if take["analysis_complete"]:
            take["findings"] = findings.get(str(take["clip_id"]), [])
    return takes


async def _fetch_windows(project_id: int, takes: list[dict], work: Path) -> dict[UUID, bytes]:
    """Assemble the window the panel watches, one take at a time.

    From the proxy, not the original — see storage.download_proxy_window for why
    that is a fairness decision rather than a shortcut.

    Failures are per-take and non-fatal. A setup where one proxy is missing is
    still worth judging on the rest, and that take then gets no verdict rather
    than the whole shot getting none.
    """
    windows: dict[UUID, bytes] = {}

    for take in takes:
        clip_id = take["clip_id"]
        try:
            segments = work / f"{clip_id}.ts"
            if not storage.download_proxy_window(
                f"p{project_id}/{clip_id}", segments, PANEL_WINDOW_S
            ):
                continue

            # Remuxed, not re-encoded. Gemini wants a container it can seek in,
            # and the video stream is already exactly what we want to send.
            window = await remux(segments, work / f"{clip_id}.mp4", PANEL_WINDOW_S)
            if window is not None:
                windows[clip_id] = window.read_bytes()
            segments.unlink(missing_ok=True)
        except Exception:
            log.exception("could not prepare take %s for the panel", clip_id)

    return windows


def _as_rows(result, takes: list[dict]) -> list[dict]:
    """Turn the chief's verdict into one row per take.

    Outcome is assigned here rather than by the model. The model says which take
    leads and why; first, second and the rest follow from the scores, and letting
    a model name its own runner-up invites it to be inconsistent with the ranking
    it just produced.

    The per-criterion scores and the safe ranges are computed here too, from the
    measurements and the findings. Asking the model for them would be asking it
    to do arithmetic it cannot check and we can.
    """
    by_clip = {t["clip_id"]: t for t in takes}
    ordered = sorted(result.verdicts, key=lambda v: v.score, reverse=True)

    runner_up = None
    for v in ordered:
        if result.winner_id is not None and v.clip_id != result.winner_id:
            runner_up = v.clip_id
            break

    rows = []
    for v in result.verdicts:
        if result.winner_id is not None and v.clip_id == result.winner_id:
            outcome = "selected"
        elif v.clip_id == runner_up:
            outcome = "runner_up"
        else:
            outcome = "not_selected"

        take = by_clip.get(v.clip_id, {})
        duration = take.get("duration_s", 0.0)

        # Findings from both sources in one list: what ffmpeg measured at ingest
        # and what the panel observed. They are the same kind of thing to
        # everything downstream, and an editor does not care which found the
        # boom in shot.
        findings = _merge_findings(take.get("findings", []), v.findings, duration)

        scores = criteria.score_take(take, findings)
        ranges, trims = ranges_service.safe_ranges(duration, findings)
        assembly = ranges_service.longest(ranges)

        rows.append(
            {
                "clip_id": v.clip_id,
                "outcome": outcome,
                "score": v.score,
                "margin": result.margin if outcome == "selected" else 0.0,
                "reason": v.reason,
                "reason_code": v.reason_code,
                "findings": findings,
                "criterion_names": scores.names,
                "criterion_scores": scores.scores,
                "safe_starts_s": [r.start_s for r in ranges],
                "safe_ends_s": [r.end_s for r in ranges],
                "trim_reasons": trims,
                # The single span an assembly would use. Zero-zero when nothing is
                # usable, which is a real answer and not a missing one.
                "in_point_s": assembly.start_s if assembly else 0.0,
                "out_point_s": assembly.end_s if assembly else 0.0,
            }
        )
    return rows


def _merge_findings(measured: list[dict], observed, duration_s: float) -> list[dict]:
    """One list from two sources, each keeping its provenance.

    Measured findings come from ffmpeg and carry a span it detected. Observed
    ones come from the panel and carry a span it claims. Both are used, and the
    source is recorded because an editor deciding whether to trust a trim should
    know whether a machine measured it or a model saw it.
    """
    out: list[dict] = []

    for f in measured:
        out.append({**f, "source": "measured"})

    for f in observed:
        where = getattr(f, "where", None)
        code = getattr(f, "code", "")
        start = float(getattr(where, "start_s", 0.0) or 0.0) if where else 0.0
        end = float(getattr(where, "end_s", 0.0) or 0.0) if where else 0.0

        # A span with no length means "throughout" — and the model has no way to
        # know how long the take is, because it never sees a duration. Widening
        # it here is the difference between a row that seeks somewhere and a row
        # that says "throughout" and does nothing when clicked.
        if end <= start:
            start, end = 0.0, duration_s

        out.append(
            {
                # The enum's value, not its repr. Everything downstream matches on
                # the taxonomy string, and a class name matches nothing — silently,
                # by scoring every take as having no findings at all.
                "code": getattr(code, "value", code),
                "detail": getattr(f, "detail", ""),
                "severity": getattr(getattr(f, "severity", None), "value", "attention"),
                "start_s": start,
                "end_s": end,
                "source": "observed",
            }
        )

    return out


async def takes_in_shot(project_id: int, group_id: int, subgroup_id: int) -> list[dict]:
    """Every take in this shot, whether or not anything has judged it.

    A comparison needs two takes. Footage does not. The cockpit was built to
    read its takes out of the verdicts, so a shot holding one clip returned no
    verdicts, drew no player, and an editor who had just uploaded a take could
    not watch it — the proxy was built and reachable the whole time.

    It also blocked the thing verdicts have nothing to do with: choosing source
    ranges. A single take is a perfectly good thing to select a range from.

    So this answers "what footage is in this shot", and the verdicts answer
    "what a comparison concluded about it". The fields a decision would have
    filled are left empty rather than invented: no score, no outcome, no
    recommendation.
    """
    ch = await client()
    result = await ch.query(
        """
        SELECT toString(clip_id), take_no, duration_ms / 1000,
               proxy_uri, sprite_uri, camera, fps, scene_code, shot_code,
               captured_at, finding_codes, finding_starts_s, finding_ends_s,
               uploaded_by, storage_uri
        FROM current_clip_placement
        WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
          AND subgroup_id = {s:UInt32} AND status = 'active'
        ORDER BY take_no, clip_id
        """,
        parameters={"p": project_id, "g": group_id, "s": subgroup_id},
    )

    takes = []
    for row in result.result_rows:
        duration_s = max(float(row[2]), 0.001)
        takes.append(
            {
                "clip_id": str(row[0]),
                "take_no": int(row[1]),
                "outcome": "",
                "score": 0.0,
                "margin": 0.0,
                "reason": "",
                "reason_code": "",
                "findings": [
                    {
                        "code": str(code),
                        "start_s": float(start),
                        "end_s": float(end),
                        "severity": "attention",
                        "detail": "",
                    }
                    for code, start, end in zip(row[10], row[11], row[12], strict=True)
                ],
                # The whole clip, because nothing has yet said any part of it is
                # unusable. An editor trims from the full duration.
                "usable_from_s": 0.0,
                "usable_to_s": duration_s,
                "decided_by": "",
                "actor": "",
                "model_id": "",
                "prompt_version": "",
                "panel_convened": False,
                "decided_at": None,
                "proxy_uri": str(row[3] or ""),
                "sprite_uri": str(row[4] or ""),
                "criteria": {},
                "safe_ranges": [{"start_s": 0.0, "end_s": duration_s}],
                "trim_reasons": [],
                "duration_s": duration_s,
                "camera": str(row[5] or ""),
                "captured_at": row[9].isoformat() if row[9] else None,
                "fps": float(row[6] or 0),
                "scene_code": str(row[7] or ""),
                "shot_code": str(row[8] or ""),
                "uploaded_by": str(row[13] or ""),
                "can_delete": False,
                "filename": str(row[14] or "").rsplit("/", 1)[-1],
            }
        )
    return takes
