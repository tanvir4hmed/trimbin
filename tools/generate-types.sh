#!/usr/bin/env bash
# Regenerate the web app's types from the API's OpenAPI schema.
#
# The TypeScript types were hand-written, mirroring thirty-three shapes that
# nothing checked. They drifted, and the drift took the workspace down: the
# project endpoint omitted `member_emails` for an anonymous caller while the
# type declared it required, so every signed-out visitor got a client-side
# exception on a page the server had answered 200.
#
# Run this after changing any response model. CI runs it too and fails if the
# committed file is stale, so a renamed Python field breaks the web build rather
# than a browser.
set -euo pipefail

cd "$(dirname "$0")/.."

# The API's interpreter, not whatever `python` happens to be. Locally that is
# the virtualenv; in CI `uv run` resolves it from api/pyproject.toml.
if [ -x api/.venv/Scripts/python.exe ]; then
    PY=api/.venv/Scripts/python.exe
elif [ -x api/.venv/bin/python ]; then
    PY=api/.venv/bin/python
else
    PY=""
fi

export_schema() {
    cat <<'SCRIPT'
import json, sys
sys.path.insert(0, "api")
from app.main import app
json.dump(app.openapi(), open("web/openapi.json", "w"), indent=1)
SCRIPT
}

if [ -n "$PY" ]; then
    export_schema | "$PY" -
else
    export_schema | (cd api && uv run python -) 
fi

cd web
npx --yes openapi-typescript openapi.json -o lib/schema.d.ts
echo "types regenerated from the live schema"
