#!/usr/bin/env bash
#
# Applies migrations in order. Run by CI after Terraform, before anything deploys
# that would read from the schema.
#
# Migrations are plain SQL and every statement is idempotent, so re-running is
# safe and re-running is the normal case — CI applies them on every push.
#
#   CLICKHOUSE_URL=https://xxx.clickhouse.cloud:8443 \
#   CLICKHOUSE_PASSWORD=... \
#   ./migrate.sh

set -euo pipefail

: "${CLICKHOUSE_URL:?CLICKHOUSE_URL is required}"
: "${CLICKHOUSE_PASSWORD:?CLICKHOUSE_PASSWORD is required}"
CLICKHOUSE_USER="${CLICKHOUSE_USER:-default}"

cd "$(dirname "$0")"

echo "Applying migrations to ${CLICKHOUSE_URL%%:*}…"

for file in migrations/*.sql; do
    echo "  → $(basename "$file")"

    # --fail-with-body so a SQL error is an error here, not a 200 with a message
    # buried in the response that a pipeline would happily ignore.
    if ! response=$(curl --silent --show-error --fail-with-body \
        --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
        --data-binary "@${file}" \
        "${CLICKHOUSE_URL}/?wait_end_of_query=1" 2>&1); then
        echo "FAILED on $(basename "$file")" >&2
        echo "$response" >&2
        exit 1
    fi
done

echo "Migrations applied."

# Prove the schema is actually usable rather than merely created. A migration
# that succeeds and leaves an unqueryable table is the failure worth catching.
echo -n "Verifying… "
curl --silent --fail --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
    --data-binary "SELECT count() FROM system.tables WHERE database = currentDatabase() AND name IN ('clips','decisions','supersessions','current_selection')" \
    "${CLICKHOUSE_URL}/" | {
        read -r count
        if [[ "$count" -eq 4 ]]; then
            echo "4/4 tables present."
        else
            echo "expected 4 tables, found ${count}" >&2
            exit 1
        fi
    }
