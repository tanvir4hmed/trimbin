-- Immutable human coverage snapshots. Firestore owns the current ordered list;
-- this table owns the history and evidence. Repeated clip_id values are valid:
-- two disjoint ranges from the same take are two different selections.
CREATE TABLE IF NOT EXISTS coverage_selection_events
(
    project_id       UInt32,
    group_id         UInt32,
    subgroup_id      UInt32,
    event_id         String,
    occurred_at      DateTime64(3),
    revision         UInt32,
    segment_count    UInt16,
    position         UInt16,
    segment_id       UUID,
    clip_id          UUID,
    source_in_s      Float32,
    source_out_s     Float32,
    take_no          UInt16,
    reason           String,
    actor_id         String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (project_id, group_id, subgroup_id, occurred_at, event_id, position);
