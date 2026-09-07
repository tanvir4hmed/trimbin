# ClickHouse archive

ClickHouse supplies the editing-intelligence and analytical layer. Operational renames, job state and Film sequence saves belong in Firestore; media bytes belong in Cloud Storage.

| Data | Purpose |
|---|---|
| clips | Media measurements and initial identity metadata |
| placements | Proposed and settled category assignments |
| decisions | Take recommendations and recorded decisions |
| analysis_runs | Version, completion and coverage of analysis |
| clip_segments / clip_moments | Searchable descriptions and timecoded content |
| finding_events | Machine observations and human review events |
| coverage_selection_events | Editorial range usage history |
| clip_lifecycle_events | Removal/restoration state |
| activity / comments | Collaboration history |

Current views resolve event history. Placement consumers use current placement rather than modifying the original clip's sorting-key fields. Event timestamps and IDs provide deterministic ordering; a ClickHouse primary key does not enforce uniqueness.

Use batched inserts for observation output. Interactive commands must not rely on ALTER TABLE UPDATE. Logical replay protection and deduplicating read models remain necessary with at-least-once processing.

## Search

Structured filters, textual evidence and vector context contribute to retrieval across clip/segment/moment read models. Runtime searches use official MCP with a restricted reader identity. Search may execute multiple bounded statements; it is not universally one table or one query.

## Measurements

The current quality report counts active real-footage clips and findings from the current completed analysis run. Synthetic project IDs are excluded. Public reports include only public projects; authenticated reports follow visibility.

Each finding's first explicit human review contributes once: confirmed unchanged versus corrected/range-adjusted/dismissed. Later confirmation of a correction does not rehabilitate the original suggestion. Unreviewed findings and creative take preferences do not enter the correctness denominator.

Legacy decision-retention views are historical analytical objects, not the current public accuracy definition. Full Film sequence revisions currently live in Firestore; they are not falsely advertised as ClickHouse events.
