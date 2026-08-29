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
    --data-binary "SELECT count() FROM system.tables WHERE database = currentDatabase() AND name IN ('clips','decisions','supersessions','current_selection','mv_current_selection','review_queue','accuracy_summary','real_clips','real_decisions','accuracy_by_project','project_corpus')" \
    "${CLICKHOUSE_URL}/")

if [[ "$count" -ne 11 ]]; then
    echo "expected 11 objects, found ${count}" >&2
    exit 1
fi
echo "${count}/11 objects present."

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
