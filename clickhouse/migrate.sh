#!/usr/bin/env bash
#
# Applies migrations in order. Run by CI after Terraform, before anything deploys
# that would read from the schema.
#
# ClickHouse's HTTP interface accepts one statement per request, so each file is
# split on statement boundaries and sent separately. Comments are stripped first —
# a `--` line containing a semicolon would otherwise split a statement in half,
# and this schema deliberately documents itself in comments.
#
# Every statement is idempotent, so re-running is safe and re-running is the
# normal case: CI applies migrations on every push.
#
#   CLICKHOUSE_URL=https://xxx.clickhouse.cloud:8443 \
#   CLICKHOUSE_PASSWORD=... \
#   ./migrate.sh

set -euo pipefail

: "${CLICKHOUSE_URL:?CLICKHOUSE_URL is required}"
: "${CLICKHOUSE_PASSWORD:?CLICKHOUSE_PASSWORD is required}"
CLICKHOUSE_USER="${CLICKHOUSE_USER:-default}"

cd "$(dirname "$0")"

run_statement() {
    local sql="$1" file="$2"
    [[ -z "${sql//[[:space:]]/}" ]] && return 0

    local response
    if ! response=$(curl --silent --show-error --fail-with-body \
        --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
        --data-binary "$sql" \
        "${CLICKHOUSE_URL}/?wait_end_of_query=1" 2>&1); then
        echo "FAILED in ${file}" >&2
        echo "${sql:0:200}…" >&2
        echo "$response" >&2
        exit 1
    fi
}

echo "Applying migrations…"

for file in migrations/*.sql; do
    echo "  → $(basename "$file")"

    # Strip line comments, then split on semicolons. awk keeps this to one pass
    # and avoids depending on a SQL parser we would then have to maintain.
    statements=$(sed 's/--.*$//' "$file")

    while IFS= read -r -d ';' statement; do
        run_statement "$statement" "$(basename "$file")"
    done <<< "$statements;"
done

# The read-only user, whose password cannot live in a migration file.
#
# Created here rather than in SQL under migrations/ because that directory is in
# git and a password in git is a password everyone has. The role and its profile
# are in 011_readonly_user.sql; only the credential is applied from a secret.
#
# Idempotent: CREATE OR REPLACE, so a rotated password takes effect on the next
# deploy without anything to remember.
if [[ -n "${CLICKHOUSE_READER_PASSWORD:-}" ]]; then
    echo "  → read-only user"
    run_statement "CREATE USER IF NOT EXISTS trimbin_reader IDENTIFIED WITH sha256_password BY '${CLICKHOUSE_READER_PASSWORD}'" "reader"
    run_statement "ALTER USER trimbin_reader IDENTIFIED WITH sha256_password BY '${CLICKHOUSE_READER_PASSWORD}'" "reader"
    run_statement "GRANT trimbin_reader TO trimbin_reader" "reader"
    run_statement "ALTER USER trimbin_reader DEFAULT ROLE trimbin_reader" "reader"
else
    echo "  ! CLICKHOUSE_READER_PASSWORD unset — MCP will have no user to connect as" >&2
fi

echo -n "Verifying… "
count=$(curl --silent --fail --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
    --data-binary "SELECT count() FROM system.tables WHERE database = currentDatabase() AND name IN ('clips','decisions','comments','supersessions','current_selection','mv_current_selection','review_queue','accuracy_summary','real_clips','real_decisions','real_comments','accuracy_by_project','project_corpus','shoot_days','activity','real_activity','placements','current_placement','current_clip_placement','placement_inbox','real_placements')" \
    "${CLICKHOUSE_URL}/")

if [[ "$count" -ne 21 ]]; then
    echo "expected 21 objects, found ${count}" >&2
    exit 1
fi
echo "${count}/21 objects present."

echo -n "Placement ordering columns... "
placement_cols=$(curl --silent --fail --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
    --data-binary "SELECT count() FROM system.columns WHERE database = currentDatabase() AND table = 'placements' AND name IN ('event_id','occurred_at')" \
    "${CLICKHOUSE_URL}/")
if [[ "$placement_cols" -ne 2 ]]; then
    echo "expected 2, found ${placement_cols} - current placement can be nondeterministic" >&2
    exit 1
fi
echo "2/2 present."

# Indexes, not only tables.
#
# The verifier counted tables and views and never counted indexes, so
# idx_embedding sat in the migration file and not on the table for weeks while
# every deploy reported success. A declaration nothing compares against is a
# claim, not a schema.
echo -n "Indexes on clips... "
indexes=$(curl --silent --fail --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}"     --data-binary "SELECT count() FROM system.data_skipping_indices WHERE database = currentDatabase() AND table = 'clips' AND name IN ('idx_embedding','idx_description','idx_duration')"     "${CLICKHOUSE_URL}/")
if [[ "$indexes" -ne 3 ]]; then
    echo "expected 3, found ${indexes} - vector or text search will scan" >&2
    exit 1
fi
echo "3/3 present."

echo -n "Ingest columns... "
ingest_cols=$(curl --silent --fail --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}"     --data-binary "SELECT count() FROM system.columns WHERE database = currentDatabase() AND table = 'clips' AND name IN ('fps','content_hash','slate_uri','scene_code','shot_code')"     "${CLICKHOUSE_URL}/")
if [[ "$ingest_cols" -ne 5 ]]; then
    echo "expected 5, found ${ingest_cols} - exports would guess the frame rate again" >&2
    exit 1
fi
echo "5/5 present."

echo -n "Camera column... "
camera=$(curl --silent --fail --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
    --data-binary "SELECT count() FROM system.columns WHERE database = currentDatabase() AND table = 'clips' AND name = 'camera'" \
    "${CLICKHOUSE_URL}/")
if [[ "$camera" -ne 1 ]]; then
    echo "missing - the shoot-day and camera filters will find nothing" >&2
    exit 1
fi
echo "present."

# The reader is a boundary, not a convenience. Without it every search falls
# back to the direct client and nothing says so out loud, so a deploy that
# failed to create it should fail here rather than quietly downgrade.
if [[ -n "${CLICKHOUSE_READER_PASSWORD:-}" ]]; then
    echo -n "Read-only user... "

    if ! curl --silent --fail --user "trimbin_reader:${CLICKHOUSE_READER_PASSWORD}"         --data-binary "SELECT count() FROM clips" "${CLICKHOUSE_URL}/" >/dev/null; then
        echo "cannot read" >&2
        exit 1
    fi

    # And genuinely cannot write. A grant that looks right and is not would let
    # a model-written statement through the one boundary that matters.
    if curl --silent --fail --user "trimbin_reader:${CLICKHOUSE_READER_PASSWORD}"         --data-binary "CREATE TABLE trimbin_reader_probe (x UInt8) ENGINE = Memory"         "${CLICKHOUSE_URL}/" >/dev/null 2>&1; then
        echo "CAN WRITE - the grant is wrong" >&2
        exit 1
    fi

    echo "reads, cannot write."
fi
