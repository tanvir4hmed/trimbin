-- Retention.
--
-- The decision log is permanent — it is the product. What expires is the bulk
-- that sits alongside it: embeddings for footage nobody selected, and the
-- descriptions of clips that lost and were never revisited.
--
-- The distinction that matters: we keep the *record* of every take forever, and
-- let go of the *heavy columns* attached to takes that went nowhere. A query two
-- years from now can still tell you take 6 existed, was rejected, and why. It
-- just will not be able to find it by visual similarity any more.

-- Embeddings are 768 floats per clip. On a large archive they dominate storage,
-- and their only use is similarity search over material still in play.
ALTER TABLE clips
    MODIFY TTL
        ingested_at + INTERVAL 90 DAY
        DELETE WHERE status = 'failed',

        ingested_at + INTERVAL 180 DAY
        RECOMPRESS CODEC(ZSTD(6));

-- decisions is never expired. This is stated as a comment rather than omitted so
-- that a future reader knows it was a decision, not an oversight.
--
--   ALTER TABLE decisions MODIFY TTL ...   -- deliberately absent
