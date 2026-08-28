"""Per-criterion scores, so a recommendation can be argued with.

A single number tells an editor who disagrees only that the system disagrees
back. Six axes tell them which one produced the answer, and that is the whole
difference between a tool and an oracle.

Four axes come from measurement and are exact. Two come from what was observed
in the footage, and are marked as such — an editor should know which of these
they are trusting a model for.

Every score is 0-1 where 1.0 is "as good as this setup gets", not "good". A
setup of seven soft takes gives its sharpest take 1.0 on focus, because the
comparison is between siblings and there is nothing else to compare to. An
absolute scale would condemn a scene for being what the DoP shot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# The axes, in the order they are stored and shown.
#
# Ordered by how defensible each is, which is also roughly Murch's order read
# upwards: the things at the top are arithmetic, the things at the bottom are
# observations. An editor scanning the list should meet the hardest evidence
# first.
AXES = ("focus", "exposure", "stability", "audio", "completion", "continuity")

MEASURED = frozenset({"focus", "exposure", "stability", "audio"})
OBSERVED = frozenset({"completion", "continuity"})

# How far from the group a take has to sit before its score falls to zero.
#
# 0.6 means a take at 60% of the group's focus, or 60% above its motion, scores
# nothing on that axis. Beyond that the take is not a variation, it is a
# different thing, and grading the difference finely serves nobody.
FULL_PENALTY_AT = 0.6

# Findings that cost a take its completion score, and what each costs.
#
# Weighted rather than binary because these are not equally bad. A take where
# the dialogue stops mid-sentence cannot be used for that line at all; a take
# with a long pre-roll is simply longer than it needs to be.
COMPLETION_COSTS = {
    "dialogue.incomplete": 0.8,
    "action.incomplete": 0.8,
    "camera.move_short": 0.5,
    "camera.focus_pull_late": 0.4,
    "frame.subject_exits": 0.4,
    "action.pre_roll": 0.1,
}

CONTINUITY_COSTS = {
    "continuity.prop": 0.5,
    "continuity.wardrobe": 0.5,
    "continuity.hair": 0.4,
    "continuity.eyeline": 0.6,
    "continuity.screen_direction": 0.7,
    "continuity.blocking": 0.4,
    "continuity.lighting": 0.4,
    "continuity.set_dressing": 0.4,
    "frame.boom_visible": 0.6,
    "frame.crew_visible": 0.7,
    "frame.shadow": 0.3,
    "frame.obstruction": 0.5,
}

# Deliberately absent from both tables: performance.note and other.
#
# performance.note is the 74% of Murch's order that belongs to a person, and a
# note that quietly moved a ranking would be this system overstepping the line
# it was built around. `other` is an observation we could not name, and scoring
# something we cannot name is scoring a guess.
#
# Both still reach the editor as findings on the take. They just carry no
# weight, and the tables above are the only place that can change.


@dataclass(slots=True)
class Scores:
    values: dict[str, float]

    @property
    def names(self) -> list[str]:
        return [a for a in AXES if a in self.values]

    @property
    def scores(self) -> list[float]:
        return [round(self.values[a], 3) for a in self.names]

    @property
    def measured_only(self) -> dict[str, float]:
        return {k: v for k, v in self.values.items() if k in MEASURED}


def score_take(measurements: dict, findings: list[dict]) -> Scores:
    """Six numbers for one take.

    measurements arrive already expressed against the setup median, so the
    comparison is baked in before this is called.
    """
    values = {
        # Sharper than the group is not better than the group. A take at 1.4x
        # the median focus is not 40% more usable, so credit stops at parity and
        # only shortfall costs anything.
        "focus": _shortfall_score(measurements.get("sharpness_rel", 1.0)),
        # Exposure is penalised in both directions: too bright loses highlights,
        # too dark loses shadow, and neither grades back.
        "exposure": _deviation_score(measurements.get("exposure_rel", 1.0))
        * _clipping_factor(measurements.get("clipping_pct", 0.0)),
        # Only excess movement costs. A locked-off take among handheld ones is
        # not a fault, and calling it one would punish the steadiest take in the
        # setup.
        "stability": _excess_score(measurements.get("motion_rel", 1.0)),
        "audio": _audio_score(
            measurements.get("audio_lufs", 0.0), measurements.get("noise_floor_db", 0.0)
        ),
        "completion": _finding_score(findings, COMPLETION_COSTS),
        "continuity": _finding_score(findings, CONTINUITY_COSTS),
    }

    dropped = int(measurements.get("dropped_frames", 0) or 0)
    if dropped:
        # Dropped frames are a recording fault, not a photographic one, and they
        # damage every axis that depends on the image being there.
        factor = max(0.0, 1.0 - min(1.0, dropped / 10) * 0.9)
        for axis in ("focus", "stability"):
            values[axis] *= factor

    return Scores({k: max(0.0, min(1.0, v)) for k, v in values.items()})


def _shortfall_score(ratio: float) -> float:
    """1.0 at or above the group median, falling as the take drops below it."""
    if ratio >= 1.0:
        return 1.0
    return max(0.0, 1.0 - (1.0 - ratio) / FULL_PENALTY_AT)


def _excess_score(ratio: float) -> float:
    """1.0 at or below the group median, falling as the take exceeds it."""
    if ratio <= 1.0:
        return 1.0
    return max(0.0, 1.0 - (ratio - 1.0) / FULL_PENALTY_AT)


def _deviation_score(ratio: float) -> float:
    """1.0 at the median, falling in either direction."""
    return max(0.0, 1.0 - abs(ratio - 1.0) / FULL_PENALTY_AT)


def _clipping_factor(pct: float) -> float:
    """Blown or crushed pixels, which no grade recovers.

    Multiplied rather than subtracted: a take that is well exposed on average
    and clipping in the highlights is not a well exposed take, and averaging
    would let the two cancel.
    """
    return max(0.0, 1.0 - min(100.0, max(0.0, pct)) / 100.0 * 2.0)


# Signal-to-noise below which hiss is audible under dialogue.
#
# Measured as the gap between programme loudness and the noise floor, not from
# the floor's absolute value. A -60 dB floor under -23 LUFS dialogue is clean;
# the same floor under -43 LUFS dialogue is audible the moment anyone normalises
# the take, which is the first thing post does.
CLEAN_SNR_DB = 30.0
POOR_SNR_DB = 12.0

# Levels that indicate a fault rather than a choice.
#
# Production sound is recorded with headroom and normalised later, so quiet is
# normal. These are the points where quiet stops meaning "conservative gain" and
# starts meaning "the microphone was not on the actor", and where loud stops
# meaning "healthy" and starts risking the peak.
BARELY_RECORDED_LUFS = -50.0
UNCOMFORTABLY_HOT_LUFS = -12.0


def _audio_score(lufs: float, noise_floor_db: float) -> float:
    """What survives post, not what meets a delivery spec.

    EBU R 128's -23 LUFS is a *delivery* standard. Production sound is recorded
    quiet on purpose and normalised later, so scoring a take against -23 marks
    down every honestly recorded take on a shoot for a property of the recording
    chain rather than of the take. That is exactly the absolute-threshold
    mistake this system exists to avoid, and it did it: every one of the twelve
    dataset takes sits between -33 and -43 LUFS and was being scored between
    0.21 and 0.47 for it.

    What actually costs an editor something is what cannot be fixed afterwards:
    hiss sitting under the dialogue, and a level so far off that the gain was
    wrong rather than cautious. Both of those are scored here.

    Still absolute rather than group-relative, and that part was right: a
    group-relative audio score would call the least-bad take in a badly recorded
    setup correct.
    """
    if lufs == 0.0:
        # No audio measured. Zero would penalise a take for a measurement we did
        # not take; 1.0 would claim it is clean. 0.5 says we do not know, and
        # the interface shows it as unmeasured.
        return 0.5

    # Noise under the dialogue, which normalising only makes louder.
    snr = lufs - noise_floor_db
    if snr >= CLEAN_SNR_DB:
        clarity = 1.0
    elif snr <= POOR_SNR_DB:
        clarity = 0.0
    else:
        clarity = (snr - POOR_SNR_DB) / (CLEAN_SNR_DB - POOR_SNR_DB)

    # Level, penalised only at the extremes where it stops being a choice.
    if lufs <= BARELY_RECORDED_LUFS:
        level = 0.3
    elif lufs >= UNCOMFORTABLY_HOT_LUFS:
        level = 0.6
    else:
        level = 1.0

    return clarity * level


def _finding_score(findings: list[dict], costs: dict[str, float]) -> float:
    """1.0 with nothing found, falling as findings accumulate.

    Costs multiply rather than sum. Two continuity problems are worse than one
    but not necessarily twice as bad, and summing lets three minor notes score a
    take below one that is genuinely unusable.
    """
    score = 1.0
    for f in findings:
        cost = costs.get(str(f.get("code", "")))
        if cost is None:
            continue
        severity = str(f.get("severity", "attention")).lower()
        weight = {"note": 0.4, "attention": 1.0, "blocking": 1.0}.get(severity, 1.0)
        score *= max(0.0, 1.0 - cost * weight)
    return score
