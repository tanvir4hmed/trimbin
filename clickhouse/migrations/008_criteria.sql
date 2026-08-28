-- Per-criterion scores, and the range each take is actually good for.
--
-- The decisions table carried one score per take. That is the thing this
-- product said it would not do: an editor who disagrees with a recommendation
-- needs to see which axis produced it, and a single number tells them only that
-- the system disagrees back.
--
-- Six axes, stored as parallel arrays rather than six columns. The set will
-- change — continuity is one axis today and will probably become several — and
-- a schema migration per axis is how a system stops adding them.
--
-- Every value is 0-1 and relative to the other takes of the same setup. An
-- absolute score would mark down all seven takes of a night scene for being
-- dark; these ask only whether a take is unlike its siblings.

ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS criterion_names Array(LowCardinality(String)) DEFAULT []
    COMMENT 'focus, exposure, stability, audio, completion, continuity';

ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS criterion_scores Array(Float32) DEFAULT [];

-- The usable material, as spans rather than one in/out pair.
--
-- in_point_s and out_point_s describe a single contiguous range, which is what
-- an assembly needs and not what a take is. A take with a focus miss in the
-- middle has two usable stretches, and collapsing them to one either throws
-- away the second or silently includes the fault between them.
--
-- Both are kept: these arrays are the truth, and in/out stays as the single
-- span an assembly would use.
ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS safe_starts_s Array(Float32) DEFAULT [];

ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS safe_ends_s Array(Float32) DEFAULT [];

-- Why the take is shorter than its duration, if it is.
--
-- Without this a trimmed range is a mystery: the interface can show that four
-- seconds went missing but not that a slate was in shot for them. An editor who
-- cannot see the reason has to go and look, which is the work this was supposed
-- to save.
ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS trim_reasons Array(LowCardinality(String)) DEFAULT [];
