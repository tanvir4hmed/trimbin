-- Loosen the reader's result cap, and say why the first value was wrong.
--
-- `max_result_rows = 1000` looked like a sensible bound on what a search should
-- return. It is not a bound on that. ClickHouse counts rows the query *produces*
-- before LIMIT is applied, so a statement that ends in `LIMIT 20` over a table
-- with a few thousand matching rows still trips it — and the server answers with
-- an exception rather than a truncated result.
--
-- The symptom was worse than the cause. mcp-clickhouse returned that exception
-- as plain text, the parser could not read it, and the search answered "nothing
-- matched" over an archive that had matches. A limit intended to protect the
-- service was silently producing wrong answers.
--
-- The real protections are the ones below it: bytes read, rows read, and
-- execution time. Those bound the work rather than the shape of the result, and
-- they cannot turn a correct query into an empty one.
--
-- The application caps what comes back at 100 rows (search.HARD_LIMIT) and the
-- MCP wrapper appends its own LIMIT. This is the outer wall, not the fence.

-- ALTER, not CREATE OR REPLACE: ClickHouse does not accept the latter for a
-- settings profile, and the parse error names the position rather than the
-- unsupported form. The profile is created in 011; this changes it.
ALTER SETTINGS PROFILE trimbin_reader_profile
SETTINGS
    readonly = 1 CONST,
    max_execution_time = 30 CONST,
    -- Generous, because it is measured before LIMIT. A search returning twenty
    -- rows can legitimately produce tens of thousands on the way there.
    max_result_rows = 1000000 CONST,
    max_result_bytes = 200000000 CONST,
    -- These are the limits that actually matter: they bound how much of the
    -- table a single statement may touch, whatever it asks for.
    max_rows_to_read = 50000000 CONST,
    max_bytes_to_read = 2000000000 CONST;
