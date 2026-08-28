-- The measurements a ratio is computed from.
--
-- The clips table stored exposure_rel, sharpness_rel and motion_rel — each take
-- expressed against its setup's median — and nothing else. That is the number
-- worth comparing, but it is derived, and the values it derives from were being
-- thrown away at ingest. A clip arriving alone was written with 1.0 in all three
-- and no way to ever compute anything better, because the absolute measurement
-- was gone.
--
-- Two consequences, both real:
--
--   Normalisation could not run. It had nothing to take a median of, so every
--   clip in the archive carried 1.0 and every comparison downstream was reading
--   a constant.
--
--   A late take could not be folded in. Takes arrive one message at a time and
--   out of order, so the median moves as a setup fills. Recomputing needs the
--   raw values; without them the only way back is re-decoding the video.
--
-- So the raw value is stored as the fact and the ratio as a view of it. The
-- units are what ffmpeg reports, deliberately not rescaled: luma on 0-255,
-- sharpness as blurdetect's inverse, motion as mean frame-to-frame difference.
-- Rescaling here would bake in an interpretation, and the whole point is that
-- interpretation happens against the group.

ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS exposure_raw Float32 DEFAULT 0
    COMMENT 'Mean luma, 0-255, as measured. Not comparable across setups.';

ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS sharpness_raw Float32 DEFAULT 0
    COMMENT 'Focus measure, higher is sharper. Only meaningful against siblings.';

ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS motion_raw Float32 DEFAULT 0
    COMMENT 'Mean frame-to-frame difference. A locked-off and a handheld shot are both correct.';

-- Where a normalised value came from, so a 1.0 can be read honestly.
--
-- 1.0 means two entirely different things: "measured, and exactly at the group
-- median" or "never normalised, nothing to compare against". An editor looking
-- at a shot cannot tell those apart, and neither could the accuracy figures.
ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS normalised_at DateTime DEFAULT toDateTime(0)
    COMMENT 'Epoch zero means the ratios are placeholders, not measurements.';

-- Timecoded findings from the measurement layer, kept on the clip.
--
-- The decisions table already carries findings, but those are the panel's, and
-- they only exist for a shot that has been judged. These are ffmpeg's: where
-- focus went, where the camera lurched, where the frame froze. They exist from
-- ingest, they are the evidence the panel is given, and an editor should be able
-- to click one before any judgement has happened at all.
ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS finding_codes Array(LowCardinality(String)) DEFAULT [];

ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS finding_starts_s Array(Float32) DEFAULT [];

ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS finding_ends_s Array(Float32) DEFAULT [];
