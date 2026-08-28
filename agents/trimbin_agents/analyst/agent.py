"""The Analyst: three specialists and a chief.

The expensive agent, and the only one whose cost scales with footage length. Two
mechanisms keep that in hand.

**Deliberation is rationed.** Where one take clearly leads â€” the others
underexposed, incomplete, or failing Tier 1 â€” measurements decide and the panel
never convenes. It sits only for genuine close calls, which is roughly one shot
in five. The hard cases are the only ones where a panel would change the answer.

**Comparison is bracketed.** Gemini accepts at most ten videos per request while
shots can run to twenty takes, so larger groups are compared in rounds with
winners advancing. Every verdict records which round produced it, so the archive
can reconstruct how a winner was reached rather than merely asserting one.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from google import genai
from google.genai import types

from ..common.errors import AgentFailure
from ..config import settings
from ..contracts.analysis import (
    AnalysisRequest,
    AnalysisResult,
    Measurements,
    SpecialistReport,
    TakeVerdict,
)
from ..contracts.base import ClipRef, Confidence, Finding, Provenance, Severity

log = logging.getLogger(__name__)

PROMPT_VERSION = "analyst/v1"
_HERE = Path(__file__).parent

TECHNICAL = (_HERE / "prompt_technical_v1.md").read_text(encoding="utf-8")
CONTINUITY = (_HERE / "prompt_continuity_v1.md").read_text(encoding="utf-8")
PERFORMANCE = (_HERE / "prompt_performance_v1.md").read_text(encoding="utf-8")
CHIEF = (_HERE / "prompt_chief_v1.md").read_text(encoding="utf-8")

# How far from the group median counts as an outlier worth mentioning. Below
# this, the takes agree and there is nothing to report â€” seven handheld takes are
# a style, not seven mistakes.
OUTLIER_RATIO = 1.6


class AnalystAgent:
    def __init__(self, client: genai.Client | None = None) -> None:
        self._client = client or genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.model_location,
        )

    async def run(self, request: AnalysisRequest, clip_bytes: dict[UUID, bytes]) -> AnalysisResult:
        """Compare the takes of one shot and return a verdict with its reasoning."""
        if len(request.clips) > settings.max_takes_per_comparison:
            return await self._bracket(request, clip_bytes)

        technical = _technical_report(request)
        leader, margin = _rank_on_measurements(request)

        if margin >= settings.panel_margin:
            return await self._fast_path(request, technical, leader, margin)

        return await self._panel(request, technical, clip_bytes)

    # -- fast path ---------------------------------------------------------

    async def _fast_path(
        self,
        request: AnalysisRequest,
        technical: list[SpecialistReport],
        leader: UUID,
        margin: float,
    ) -> AnalysisResult:
        """One take is clearly ahead. Measurements decide; no video is sent.

        This is where most shots land, and skipping the panel here is what makes
        the whole pipeline affordable. Sending seven videos to settle a question
        the numbers already answered would spend the budget on shots nobody was
        going to argue about.
        """
        verdicts = [
            TakeVerdict(
                clip_id=clip.clip_id,
                score=_score(request.measurements[clip.clip_id]),
                reason=(
                    "cleanest complete take"
                    if clip.clip_id == leader
                    else _shortfall(request.measurements[clip.clip_id])
                ),
                reason_code="selected.clean" if clip.clip_id == leader else "measurement.behind",
                findings=_findings_for(clip.clip_id, technical),
            )
            for clip in request.clips
        ]

        return AnalysisResult(
            subgroup_id=request.clips[0].subgroup_id,
            verdicts=verdicts,
            winner_id=leader,
            margin=margin,
            rationale=(
                f"Take {_take_of(leader, request)} leads on measurements by "
                f"{margin:.0%}; the panel was not needed."
            ),
            specialist_reports=technical,
            confidence=Confidence.CONFIDENT,
            provenance=_provenance(request),
        )

    # -- full panel --------------------------------------------------------

    async def _panel(
        self,
        request: AnalysisRequest,
        technical: list[SpecialistReport],
        clip_bytes: dict[UUID, bytes],
    ) -> AnalysisResult:
        """The takes are technically equivalent, so the reasons have to be found.

        Continuity and performance run concurrently: they watch the same footage
        and neither depends on the other's answer, so waiting for one before
        starting the other would double the latency of the slowest step for
        nothing.
        """
        parts = [
            types.Part.from_bytes(data=clip_bytes[c.clip_id], mime_type="video/mp4")
            for c in request.clips
            if c.clip_id in clip_bytes
        ]

        continuity, performance = await asyncio.gather(
            self._specialist(CONTINUITY, parts, request),
            self._specialist(PERFORMANCE, parts, request),
        )

        reports = technical + continuity + performance
        return await self._chief(request, reports)

    async def _specialist(
        self,
        prompt: str,
        parts: list[types.Part],
        request: AnalysisRequest,
    ) -> list[SpecialistReport]:
        try:
            response = await self._client.aio.models.generate_content(
                model=settings.analyst_model,
                contents=[*parts, prompt, _describe_takes(request)],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=list[SpecialistReport],
                    temperature=0.1,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise AgentFailure(f"specialist failed: {exc}") from exc

        return [SpecialistReport.model_validate(r) for r in _loads(response.text)]

    async def _chief(
        self,
        request: AnalysisRequest,
        reports: list[SpecialistReport],
    ) -> AnalysisResult:
        """Weigh the reports. No video: the chief judges testimony, not footage.

        Sending the clips again would let the chief form its own impressions and
        quietly override the specialists it exists to arbitrate between â€” and it
        would pay for the same tokens twice.
        """
        try:
            response = await self._client.aio.models.generate_content(
                model=settings.analyst_model,
                contents=[
                    CHIEF,
                    _describe_takes(request),
                    _render_reports(reports),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AnalysisResult,
                    temperature=0.1,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise AgentFailure(f"chief failed: {exc}") from exc

        result = AnalysisResult.model_validate_json(response.text)

        # The model supplies judgement and language. Provenance and the specialist
        # reports are ours to attach, so they cannot be paraphrased or dropped.
        return result.model_copy(
            update={
                "specialist_reports": reports,
                "provenance": _provenance(request),
                "subgroup_id": request.clips[0].subgroup_id,
            }
        )

    # -- bracketing --------------------------------------------------------

    async def _bracket(
        self,
        request: AnalysisRequest,
        clip_bytes: dict[UUID, bytes],
    ) -> AnalysisResult:
        """Compare in rounds when the group is larger than a single request.

        Losers keep the verdict from the round they lost in, so a take eliminated
        early still carries a reason an editor can read. Dropping those would
        leave gaps in the archive exactly where someone later asks "why not this
        one?"
        """
        size = settings.max_takes_per_comparison
        heats = [request.clips[i : i + size] for i in range(0, len(request.clips), size)]

        all_verdicts: list[TakeVerdict] = []
        all_reports: list[SpecialistReport] = []
        survivors: list[ClipRef] = []

        for heat in heats:
            sub = request.model_copy(
                update={
                    "clips": heat,
                    "measurements": {c.clip_id: request.measurements[c.clip_id] for c in heat},
                    "bracket_round": request.bracket_round,
                }
            )
            result = await self.run(sub, clip_bytes)
            all_verdicts.extend(result.verdicts)
            all_reports.extend(result.specialist_reports)

            if result.winner_id:
                survivors.extend(c for c in heat if c.clip_id == result.winner_id)

        if not survivors:
            return AnalysisResult(
                subgroup_id=request.clips[0].subgroup_id,
                verdicts=all_verdicts,
                winner_id=None,
                margin=0.0,
                rationale="No take in any heat was usable.",
                specialist_reports=all_reports,
                confidence=Confidence.UNCERTAIN,
                provenance=_provenance(request),
            )

        if len(survivors) == 1:
            final_id, final_margin = survivors[0].clip_id, 1.0
            rationale = "Single survivor across heats."
        else:
            final = await self.run(
                request.model_copy(
                    update={
                        "clips": survivors,
                        "measurements": {c.clip_id: request.measurements[c.clip_id] for c in survivors},
                        "bracket_round": request.bracket_round + 1,
                    }
                ),
                clip_bytes,
            )
            final_id, final_margin = final.winner_id, final.margin
            rationale = final.rationale
            all_reports.extend(final.specialist_reports)
            # The final round's verdicts supersede the heat verdicts for the
            # takes that reached it.
            reached = {v.clip_id for v in final.verdicts}
            all_verdicts = [v for v in all_verdicts if v.clip_id not in reached] + final.verdicts

        return AnalysisResult(
            subgroup_id=request.clips[0].subgroup_id,
            verdicts=all_verdicts,
            winner_id=final_id,
            margin=final_margin,
            rationale=f"{len(request.clips)} takes compared in {len(heats)} heats. {rationale}",
            specialist_reports=all_reports,
            confidence=Confidence.CONFIDENT if final_id else Confidence.UNCERTAIN,
            provenance=_provenance(request),
        )


# ---------------------------------------------------------------------------
# Measurement handling. Deliberately not a model's job â€” these are arithmetic,
# and a language model asked to compare two numbers is slower, dearer and less
# reliable than comparing two numbers.
# ---------------------------------------------------------------------------


def _score(m: Measurements) -> float:
    """Technical cleanliness on 0â€“1. Explicitly not a judgement of performance.

    Takes no context because it needs none: the measurements arrive already
    expressed as ratios against the group median, so the comparison is baked in
    before this is called. That is what stops a deliberately dark scene having
    every take marked down for being dark â€” all seven sit at 1.0, and only a
    take darker than its siblings falls below.
    """
    penalties = [
        abs(m.exposure_rel - 1.0) * 0.5,
        m.clipping_pct / 100 * 0.8,
        max(0.0, 1.0 - m.sharpness_rel) * 0.6,
        max(0.0, m.motion_rel - 1.0) * 0.35,
        min(1.0, m.dropped_frames / 10) * 0.9,
    ]
    return max(0.0, min(1.0, 1.0 - sum(penalties)))


def _rank_on_measurements(request: AnalysisRequest) -> tuple[UUID, float]:
    scored = sorted(
        ((c.clip_id, _score(request.measurements[c.clip_id])) for c in request.clips),
        key=lambda pair: pair[1],
        reverse=True,
    )
    if len(scored) == 1:
        return scored[0][0], 1.0
    return scored[0][0], round(scored[0][1] - scored[1][1], 4)


def _technical_report(request: AnalysisRequest) -> list[SpecialistReport]:
    """Built from measurements without a model call.

    The technical specialist has nothing to infer: the numbers are already exact.
    Paying a model to restate them would add cost, latency and the possibility of
    being wrong about arithmetic.
    """
    reports: list[SpecialistReport] = []

    for clip in request.clips:
        m = request.measurements[clip.clip_id]
        findings: list[Finding] = []

        if m.motion_rel >= OUTLIER_RATIO:
            findings.append(
                Finding(
                    code="stability.outlier",
                    detail=f"most camera movement in this group, {m.motion_rel:.1f}x the median",
                    severity=Severity.NOTE,
                )
            )
        if m.exposure_rel <= 1 / OUTLIER_RATIO:
            findings.append(
                Finding(
                    code="exposure.under",
                    detail=f"darkest take in this group, {m.exposure_rel:.2f} of the median",
                    severity=Severity.NOTE,
                )
            )
        # The bright end matters more, not less: a dark image can be lifted in
        # the grade, a clipped one has nothing left to lift.
        if m.exposure_rel >= OUTLIER_RATIO:
            findings.append(
                Finding(
                    code="exposure.over",
                    detail=f"brightest take in this group, {m.exposure_rel:.1f}x the median",
                    severity=Severity.ATTENTION,
                )
            )
        if m.clipping_pct > 5:
            findings.append(
                Finding(
                    code="exposure.clipped",
                    detail=f"{m.clipping_pct:.1f}% of frames clipped",
                    severity=Severity.ATTENTION,
                )
            )
        if m.sharpness_rel <= 1 / OUTLIER_RATIO:
            findings.append(
                Finding(
                    code="focus.soft",
                    detail=f"softest take in this group, {m.sharpness_rel:.2f} of the median",
                    severity=Severity.ATTENTION,
                )
            )
        if m.dropped_frames:
            findings.append(
                Finding(
                    code="frames.dropped",
                    detail=f"{m.dropped_frames} dropped frames",
                    severity=Severity.BLOCKING,
                )
            )

        reports.append(
            SpecialistReport(
                clip_id=clip.clip_id,
                findings=findings,
                confidence=Confidence.CONFIDENT,
                summary=(
                    "within the group on every measured axis"
                    if not findings
                    else "; ".join(f.detail for f in findings)[:200]
                ),
            )
        )

    return reports


def _shortfall(m: Measurements) -> str:
    """Why this take is behind, in the group's own terms."""
    gaps = {
        "darker than the rest of the group": 1.0 - m.exposure_rel,
        "softer focus than the rest of the group": 1.0 - m.sharpness_rel,
        "more camera movement than the rest of the group": m.motion_rel - 1.0,
        "clipped highlights": m.clipping_pct / 100,
    }
    worst = max(gaps.items(), key=lambda pair: pair[1])
    return worst[0] if worst[1] > 0.05 else "narrowly behind on measurements"


def _findings_for(clip_id: UUID, reports: list[SpecialistReport]) -> list[Finding]:
    return [f for r in reports if r.clip_id == clip_id for f in r.findings]


def _take_of(clip_id: UUID, request: AnalysisRequest) -> int:
    return next((c.take_no for c in request.clips if c.clip_id == clip_id), 0)


def _describe_takes(request: AnalysisRequest) -> str:
    lines = [f"Shot has {len(request.clips)} takes."]
    if request.look_profile:
        lines.append(f"Declared look: {request.look_profile}.")
    for clip in request.clips:
        m = request.measurements[clip.clip_id]
        lines.append(
            f"Take {clip.take_no} ({clip.clip_id}): {m.duration_s:.1f}s, "
            f"exposure {m.exposure_rel:.2f}x, sharpness {m.sharpness_rel:.2f}x, "
            f"motion {m.motion_rel:.2f}x median."
        )
    return "\n".join(lines)


def _render_reports(reports: list[SpecialistReport]) -> str:
    lines = ["Specialist reports:"]
    for r in reports:
        lines.append(f"\n{r.clip_id} [{r.confidence.value}]: {r.summary}")
        for f in r.findings:
            where = f" ({f.where.start_s:.1f}s-{f.where.end_s:.1f}s)" if f.where else ""
            lines.append(f"  - [{f.severity.value}] {f.code}: {f.detail}{where}")
    return "\n".join(lines)


def _provenance(request: AnalysisRequest) -> Provenance:
    ids = "".join(sorted(str(c.clip_id) for c in request.clips))
    return Provenance(
        model_id=settings.analyst_model,
        prompt_version=PROMPT_VERSION,
        produced_at=datetime.now(UTC),
        run_hash=f"{abs(hash((ids, PROMPT_VERSION, settings.analyst_model))):016x}",
    )


def _loads(text: str) -> list[dict]:
    import json

    data = json.loads(text)
    return data if isinstance(data, list) else [data]
