-- The vector index the schema has claimed since the first week.
--
-- `001_clips.sql` declares `idx_embedding` inside CREATE TABLE IF NOT EXISTS.
-- The index was added to that file after the table already existed, so every
-- subsequent run of the migration found the table present and did nothing. The
-- declaration and the deployed table have disagreed ever since:
--
--   SELECT name FROM system.data_skipping_indices WHERE table = 'clips'
--   -> idx_description, idx_duration
--
-- No error, no warning, and a README claiming vector search. This is the shape
-- of failure that migrations run with IF NOT EXISTS produce: the file is the
-- intention, the table is the fact, and nothing compares them. The verifier in
-- migrate.sh counts tables and views; it has never counted indexes.
--
-- ADD INDEX affects parts written afterwards. Existing parts are not indexed
-- until MATERIALIZE INDEX, which is a mutation over the whole table — and there
-- is nothing to gain from running it here, because 2 of 306,230 rows currently
-- hold a non-zero embedding. The backfill is P3; this is the schema catching up
-- with what it has been claiming.

ALTER TABLE clips
    ADD INDEX IF NOT EXISTS idx_embedding embedding
    TYPE vector_similarity('hnsw', 'cosineDistance', 768) GRANULARITY 1;
