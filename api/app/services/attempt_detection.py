"""Source-time performance proposals and conservative overlap reconciliation."""

from __future__ import annotations

from uuid import UUID, uuid5


def absolute_attempts(observation, window, segment_id: UUID) -> list[dict]:
    result = []
    for attempt in getattr(observation, "attempts", []):
        start = max(0.0, min(attempt.where.start_s, window.duration_s))
        end = max(0.0, min(attempt.where.end_s, window.duration_s))
        if end - start < 0.05:
            continue
        result.append(
            {
                **attempt.model_dump(exclude={"where"}),
                "start_s": round(window.start_s + start, 3),
                "end_s": round(window.start_s + end, 3),
                "evidence_segment_ids": [segment_id],
            }
        )
    return result


def consolidate_attempts(candidates: list[dict], run_id: UUID) -> list[dict]:
    """Merge only overlapping evidence of the same pass, never adjacent repeats.

    Incompatible descriptions/boundaries stay separate proposals for a human;
    no attempt to infer action equivalence from an arbitrary embedding cutoff.
    """
    result: list[dict] = []
    for item in sorted(candidates, key=lambda row: (row["start_s"], row["end_s"])):
        item = dict(item)
        for prior in result:
            overlap = min(prior["end_s"], item["end_s"]) - max(prior["start_s"], item["start_s"])
            shorter = min(prior["end_s"] - prior["start_s"], item["end_s"] - item["start_s"])
            same_action = prior["action"].strip().casefold() == item["action"].strip().casefold()
            different_window = set(prior["evidence_segment_ids"]).isdisjoint(
                item["evidence_segment_ids"]
            )
            continuation = prior["ends_after_window"] and item["starts_before_window"]
            if (
                overlap <= 0
                or (overlap / shorter < 0.65 and not continuation)
                or not same_action
                or not different_window
            ):
                continue
            if item["end_s"] > prior["end_s"]:
                prior["ends_after_window"] = item["ends_after_window"]
            prior["end_s"] = max(prior["end_s"], item["end_s"])
            prior["evidence_segment_ids"] = list(
                dict.fromkeys(prior["evidence_segment_ids"] + item["evidence_segment_ids"])
            )
            prior["confidence"] = min(prior["confidence"], item["confidence"])
            break
        else:
            result.append(item)
    for item in result:
        item["attempt_id"] = uuid5(
            run_id, f"attempt/{item['start_s']:.3f}/{item['end_s']:.3f}/{item['action']}"
        )
    return result
