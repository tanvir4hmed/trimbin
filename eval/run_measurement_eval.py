"""Does the measurement layer find the faults we planted?

This is the honest half of the accuracy claim. The live number measures whether
editors disagreed with us; this measures whether we found something we know is
there, because we put it there at a timecode we chose.

Only the deterministic layer is under test here — ffmpeg, not the model. That is
deliberate: these measurements are the foundation everything else rests on, they
cost nothing to run, and a regression in them would quietly poison every
judgement downstream while the model appeared to be at fault.

    python run_measurement_eval.py --clips fixtures/clips
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.services.ffmpeg_ops import analyse  # noqa: E402
from app.services.measure import RawMeasurements  # noqa: E402

# A finding this far from where the fault was planted still counts as finding it.
# An editor clicking a timecode wants to land in the problem, not beside it; two
# seconds is close enough to be useful and tight enough to be meaningful.
TOLERANCE_S = 2.0

# What counts as an outlier. Matches the analyst's threshold, because a fixture
# that the eval calls a hit and the pipeline calls unremarkable would be
# measuring nothing.
OUTLIER_RATIO = 1.6


@dataclass
class Case:
    fixture_id: str
    axis: str
    expected: bool
    detected: bool
    expected_start_s: float
    detected_start_s: float
    within_tolerance: bool
    note: str


def _relative(values: dict[str, float]) -> dict[str, float]:
    """Express each take against the median of the group.

    The pipeline compares takes to their siblings rather than to an absolute
    standard, so the eval has to do the same. Grading a fixture against a fixed
    threshold would test a system we did not build.
    """
    ordered = sorted(values.values())
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    if median == 0:
        return {k: 1.0 for k in values}
    return {k: v / median for k, v in values.items()}


def _detect(
    m: RawMeasurements,
    exposure_rel: float,
    sharpness_rel: float,
    motion_rel: float,
) -> dict[str, tuple[bool, float]]:
    """What the pipeline would report for this take, per axis."""
    findings: dict[str, tuple[bool, float]] = {}

    findings["stability"] = (motion_rel >= OUTLIER_RATIO, _first(m.motion_spikes))

    # Both ends. Only checking the dark side would let an overexposed take pass
    # unremarked, and blown highlights are the less recoverable of the two — a
    # dark image can be lifted, a clipped one has nothing left to lift.
    findings["exposure"] = (
        exposure_rel <= 1 / OUTLIER_RATIO
        or exposure_rel >= OUTLIER_RATIO
        or m.highlight_clip_pct > 5
        or m.shadow_clip_pct > 20,
        0.0,
    )
    findings["focus"] = (
        sharpness_rel <= 1 / OUTLIER_RATIO or bool(m.focus_loss_spans),
        _first(m.focus_loss_spans),
    )

    completion_spans = m.freeze_spans + m.black_spans
    findings["completion"] = (bool(completion_spans), _first(completion_spans))

    return findings


def _first(spans: list) -> float:
    return spans[0].start_s if spans else 0.0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clips", type=Path, default=Path("fixtures/clips"))
    parser.add_argument("--json", type=Path, help="write results for the accuracy page")
    args = parser.parse_args()

    manifest = json.loads((args.clips / "manifest.json").read_text(encoding="utf-8"))

    print("Measuring…")
    measured: dict[str, RawMeasurements] = {}
    for entry in manifest:
        path = args.clips / entry["file"]
        measured[entry["fixture_id"]] = await analyse(path)
        print(f"  {entry['fixture_id']}")

    # Normalise across the group, exactly as ingest does once a shot is complete.
    exposure_rel = _relative({k: max(m.mean_luma, 0.001) for k, m in measured.items()})
    sharpness_rel = _relative({k: max(m.sharpness, 0.001) for k, m in measured.items()})
    motion_rel = _relative({k: max(m.motion_mean, 0.001) for k, m in measured.items()})

    cases: list[Case] = []
    for entry in manifest:
        fid = entry["fixture_id"]
        m = measured[fid]
        detected = _detect(m, exposure_rel[fid], sharpness_rel[fid], motion_rel[fid])
        planted = {f["axis"]: f for f in entry["faults"]}

        for axis, (was_detected, at) in detected.items():
            fault = planted.get(axis)
            expected = fault is not None
            expected_start = fault["start_s"] if fault else 0.0
            cases.append(
                Case(
                    fixture_id=fid,
                    axis=axis,
                    expected=expected,
                    detected=was_detected,
                    expected_start_s=expected_start,
                    detected_start_s=at,
                    within_tolerance=(
                        expected and was_detected and abs(at - expected_start) <= TOLERANCE_S
                    ),
                    note=fault["detail"] if fault else "",
                )
            )

    _report(cases)

    if args.json:
        args.json.write_text(
            json.dumps([c.__dict__ for c in cases], indent=2), encoding="utf-8"
        )

    # Missed faults fail the run; false alarms are reported but tolerated. They
    # are not equally bad: a missed problem reaches the cut, while a false alarm
    # costs an editor ten seconds.
    missed = [c for c in cases if c.expected and not c.detected]
    return 1 if missed else 0


def _report(cases: list[Case]) -> None:
    print("\n" + "─" * 64)
    hits = [c for c in cases if c.expected and c.detected]
    missed = [c for c in cases if c.expected and not c.detected]
    false_alarms = [c for c in cases if not c.expected and c.detected]

    planted = len(hits) + len(missed)
    print(f"planted faults      {planted}")
    print(f"  found             {len(hits)}")
    print(f"  missed            {len(missed)}")
    print(f"false alarms        {len(false_alarms)}")

    if hits:
        on_time = sum(1 for c in hits if c.within_tolerance)
        print(f"timecode within {TOLERANCE_S:.0f}s  {on_time}/{len(hits)}")

    if missed:
        print("\nMissed — these reach the cut:")
        for c in missed:
            print(f"  {c.fixture_id:<28} {c.axis:<12} {c.note}")

    if false_alarms:
        print("\nFalse alarms — these cost attention:")
        for c in false_alarms:
            print(f"  {c.fixture_id:<28} {c.axis}")

    print("─" * 64)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
