"""Typed contracts for every agent boundary.

Import from here rather than from the submodules, so the set of things that may
cross between agents stays visible in one place.
"""

from .analysis import (
    AnalysisRequest,
    AnalysisResult,
    Measurements,
    SpecialistReport,
    TakeVerdict,
)
from .base import (
    Actor,
    ClipRef,
    Confidence,
    Finding,
    FindingCode,
    Provenance,
    ReasonCode,
    Severity,
    Strict,
    TimeRange,
)
from .segments import SegmentObservation

__all__ = [
    "Actor",
    "AnalysisRequest",
    "AnalysisResult",
    "ClipRef",
    "Confidence",
    "Finding",
    "FindingCode",
    "Measurements",
    "Provenance",
    "ReasonCode",
    "SegmentObservation",
    "Severity",
    "SpecialistReport",
    "Strict",
    "TakeVerdict",
    "TimeRange",
]
