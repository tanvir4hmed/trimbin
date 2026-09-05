#!/usr/bin/env bash
#
# One command that runs every gate a release has to pass.
#
# These checks all existed and were run by hand, in whatever order somebody
# remembered, which is how a build shipped with a React hooks violation that
# `tsc` and `next build` are both structurally blind to. A checklist that lives
# in someone's head is not a checklist.
#
# Exits non-zero on the first failure and says which gate failed. Run from the
# repository root.

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

if [ -x api/.venv/Scripts/python.exe ]; then
    PY=api/.venv/Scripts/python.exe
elif [ -x api/.venv/bin/python ]; then
    PY=api/.venv/bin/python
else
    echo "FAIL  no API virtualenv; run the project setup first"
    exit 1
fi

failed=0
step() {
    local name="$1"; shift
    printf '%-34s' "$name"
    if output=$("$@" 2>&1); then
        echo "ok"
    else
        echo "FAILED"
        echo "$output" | tail -20 | sed 's/^/      /'
        failed=1
    fi
}

echo "── Trimbin release check ──"

step "API tests"            "$PY" -m pytest api/tests -q
step "Agents tests"         bash -c "cd agents && ../$PY -m pytest -q"
step "Ruff lint"            "$PY" -m ruff check api agents
step "Ruff format"          "$PY" -m ruff format --check api agents

# The generated client must match the API it is generated from. A stale
# schema.d.ts compiles perfectly against a description that is no longer true,
# which is exactly how a required field went missing and took two screens down.
step "Generated schema fresh" bash -c '
    cp web/lib/schema.d.ts /tmp/schema.before 2>/dev/null || true
    bash tools/generate-types.sh >/dev/null 2>&1
    if ! diff -q /tmp/schema.before web/lib/schema.d.ts >/dev/null 2>&1; then
        echo "schema.d.ts was stale; regenerate and commit it"
        exit 1
    fi'

step "Web typecheck"        bash -c "cd web && npx tsc --noEmit"
step "Web build"            bash -c "cd web && npm run build"

# Terraform is the only path to infrastructure, so a malformed change is a
# failed deploy rather than a failed apply.
step "Terraform format"     terraform fmt -check -recursive
step "Terraform validate"   bash -c "cd infra/envs/demo && terraform validate"

# Every migration must be numbered uniquely, or two of them race for the same
# slot and one silently never runs.
step "Migration numbering"  bash -c '
    dupes=$(ls clickhouse/migrations/*.sql | sed "s|.*/\([0-9]*\)_.*|\1|" | sort | uniq -d)
    if [ -n "$dupes" ]; then echo "duplicate migration numbers: $dupes"; exit 1; fi'

echo "───────────────────────────"
if [ "$failed" -eq 0 ]; then
    echo "All gates passed."
    echo
    echo "Not covered here, and still required before calling a build releasable:"
    echo "  · a browser pass over every route, including a shot URL — a green"
    echo "    build says nothing about a runtime React error"
    echo "  · a public demo project that a signed-out visitor can actually open"
    echo "  · ClickHouse migrations applied against production"
else
    echo "Release check FAILED."
fi
exit "$failed"
