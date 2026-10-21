"""Paired recording-level evaluation; never promotes a model from fixtures or averages alone."""

from __future__ import annotations

import random
from collections import defaultdict
from statistics import mean
from typing import Literal

from pydantic import Field, model_validator

from .contracts import SHA256, Contract, fingerprint


class Case(Contract):
    id: str = Field(min_length=1)
    group: str = Field(min_length=1)
    source_sha256: str = Field(pattern=SHA256)
    split: Literal["development", "held_out"]
    rights_reference: str = Field(min_length=1)
    annotation_reference: str = Field(min_length=1)


class Metric(Contract):
    id: str = Field(min_length=1)
    direction: Literal["higher", "lower"]
    critical: bool
    primary: bool
    meaningful_improvement: float = Field(gt=0)


class EvaluationManifest(Contract):
    version: Literal["evaluation-v1"] = "evaluation-v1"
    frozen_at: str = Field(min_length=1)
    cases: list[Case] = Field(min_length=1)
    metrics: list[Metric] = Field(min_length=1)
    minimum_independent_groups: int = Field(default=30, ge=2)
    baseline_provenance_reference: str = Field(min_length=1)
    candidate_identity_reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def split_integrity(self) -> EvaluationManifest:
        if len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case ID")
        if len({m.id for m in self.metrics}) != len(self.metrics):
            raise ValueError("Duplicate metric ID")
        groups: dict[str, str] = {}
        sources: dict[str, str] = {}
        for case in self.cases:
            for registry, key in ((groups, case.group), (sources, case.source_sha256)):
                if key in registry and registry[key] != case.split:
                    raise ValueError("Recording/setup crosses development and holdout")
                registry[key] = case.split
        if not any(m.primary for m in self.metrics) or not any(m.critical for m in self.metrics):
            raise ValueError("Declare primary and critical metrics before evaluation")
        return self


class Score(Contract):
    case_id: str
    metric_id: str
    baseline: float
    candidate: float
    baseline_run: str = Field(min_length=1)
    candidate_run: str = Field(min_length=1)
    live_provenance_verified: bool
    contract_valid: bool


class Scores(Contract):
    manifest_sha256: str = Field(pattern=SHA256)
    rows: list[Score]


def paired_report(manifest: EvaluationManifest, scores: Scores, split: str) -> dict:
    if scores.manifest_sha256 != fingerprint(manifest.model_dump(mode="json")):
        raise ValueError("Scores belong to another frozen manifest")
    if split not in {"development", "held_out"}:
        raise ValueError("Unknown split")
    cases = {c.id: c for c in manifest.cases if c.split == split}
    metrics = {m.id: m for m in manifest.metrics}
    if not cases:
        raise ValueError("Split has no cases")
    rows = {(r.case_id, r.metric_id): r for r in scores.rows}
    expected = {(case, metric) for case in cases for metric in metrics}
    if len(rows) != len(scores.rows) or set(rows) != expected:
        raise ValueError("Every declared case/metric pair requires exactly one score")
    report = {
        "manifest_sha256": scores.manifest_sha256,
        "split": split,
        "status": "inconclusive",
        "release_approved": False,
        "metrics": {},
        "limitations": [],
        "remaining_gates": [
            "provenance_audit",
            "blind_editor_review",
            "licenses_and_rules",
            "end_to_end_pipeline",
            "held_out_integrity",
        ],
    }
    if any(not r.contract_valid for r in scores.rows):
        report["status"] = "failed"
        report["limitations"].append("Invalid output in declared comparison")
    live = all(r.live_provenance_verified for r in scores.rows)
    if not live:
        report["limitations"].append("Fixture/unverified provenance cannot establish quality")
    improved = False
    all_critical_clear = True
    for metric in manifest.metrics:
        grouped: dict[str, list[float]] = defaultdict(list)
        for case in cases.values():
            row = rows[case.id, metric.id]
            delta = row.candidate - row.baseline
            grouped[case.group].append(delta if metric.direction == "higher" else -delta)
        deltas = [mean(values) for _, values in sorted(grouped.items())]
        rng = random.Random(20261021)
        bootstrap = sorted(mean(rng.choices(deltas, k=len(deltas))) for _ in range(2000))
        low, high = bootstrap[50], bootstrap[1949]
        enough = len(deltas) >= manifest.minimum_independent_groups
        # Critical regressions cannot be hidden by gains on other cases or categories.
        regression = metric.critical and any(
            value < 0 for values in grouped.values() for value in values
        )
        if regression:
            report["status"] = "failed"
        if metric.critical and (not enough or low < 0 or regression):
            all_critical_clear = False
        improved |= metric.primary and enough and low >= metric.meaningful_improvement
        report["metrics"][metric.id] = {
            "cases": len(cases),
            "independent_groups": len(deltas),
            "oriented_mean_delta": mean(deltas),
            "bootstrap_95_interval": [low, high],
            "sufficient_groups": enough,
            "observed_critical_regression": regression,
        }
    if report["status"] != "failed" and live and improved and all_critical_clear:
        report["status"] = "pending_independent_review"
    if split == "development":
        report["limitations"].append("Development comparison is not held-out release evidence")
    report["limitations"].append(
        "Scores and provenance flags require audit; group minimum is not a statistical power proof"
    )
    return report


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Whitespace-token WER; select CER/another tokenizer explicitly for other languages."""
    expected, actual = reference.split(), hypothesis.split()
    previous = list(range(len(actual) + 1))
    for index, token in enumerate(expected, start=1):
        current = [index]
        for column, other in enumerate(actual, start=1):
            current.append(
                min(current[-1] + 1, previous[column] + 1, previous[column - 1] + (token != other))
            )
        previous = current
    return previous[-1] / max(1, len(expected))


def blind_pairs(
    baseline: dict[str, str], candidate: dict[str, str], seed: int
) -> tuple[list, dict]:
    if set(baseline) != set(candidate):
        raise ValueError("Blind review requires the same cases")
    rng = random.Random(seed)
    ids = sorted(baseline)
    rng.shuffle(ids)
    review, key = [], {}
    for index, case in enumerate(ids):
        swap = bool(rng.getrandbits(1))
        pair_id = f"pair-{index + 1}"
        review.append(
            {
                "id": pair_id,
                "A": candidate[case] if swap else baseline[case],
                "B": baseline[case] if swap else candidate[case],
                "decision": None,
                "reason": "",
                "disagreements": [],
            }
        )
        key[pair_id] = {"case_id": case, "A": "candidate" if swap else "baseline"}
    return review, key
