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

echo -n "Verifying… "
count=$(curl --silent --fail --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
    --data-binary "SELECT count() FROM system.tables WHERE database = currentDatabase() AND name IN ('clips','decisions','supersessions','current_selection','mv_current_selection','review_queue','accuracy_summary')" \
    "${CLICKHOUSE_URL}/")

if [[ "$count" -eq 7 ]]; then
    echo "7/7 objects present."
else
    echo "expected 7 objects, found ${count}" >&2
    exit 1
fi
