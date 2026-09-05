ALTER TABLE coverage_selection_events
    ADD COLUMN IF NOT EXISTS segment_reason String DEFAULT '',
    ADD COLUMN IF NOT EXISTS segment_origin LowCardinality(String) DEFAULT 'human',
    ADD COLUMN IF NOT EXISTS segment_created_by String DEFAULT '';
