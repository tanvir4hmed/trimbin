-- Preserve structured source-window evidence before overlap consolidation.
-- Contains model output fields, not private reasoning traces.
ALTER TABLE clip_segments ADD COLUMN IF NOT EXISTS observation_json String DEFAULT '{}';
