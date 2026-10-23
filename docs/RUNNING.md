# Running, building and operating Trimbin

Updated 23 October 2026. The running cloud application is https://trimbin.qleam.com. Use credentials supplied privately by the operator; API keys and the owner password are not public test credentials. Judge access and demo recording remain separate preparation items.

## Use the hosted application

1. Sign in and open an authorized project. Use cleared media; the verification workspace contains generated footage, not a recovered film corpus.
2. Upload through resumable chunks or choose a deployment root already authorized by an operator. A browser's local folder path is not a server mount.
3. Wait for indexing/derivatives and request analysis. Inspect the actual model/run state; failed or unavailable analysis is not a successful fixture result.
4. Review/correct findings and select valid source ranges. Prepare source timing, assemble a scene/film timeline and save its revision.
5. Export the saved revision as native/FCP7 ZIP or render supported SDR MP4. Download and inspect outputs. Actual Premiere import/relink is an additional acceptance step.

See [media](MEDIA_SETUP.md), [evidence](EVIDENCE_SETUP.md), [timeline](TIMELINE_SETUP.md), [editable output](EDITABLE_EXPORT_SETUP.md) and [render](RENDER_SETUP.md) for exact limits.

## Development checks and source builds

Required: Git, Python 3.12, uv, Node.js 22/npm, FFmpeg/ffprobe; Linux Docker Engine + Compose v2 for actual containers/databases. Windows needs a functioning Linux container backend for local container execution. The cloud host was used for runtime verification because the development PC does not have one.

```powershell
git clone https://github.com/tanvir4hmed/trimbin.git
cd trimbin
uv sync --project api --python 3.12 --all-extras --dev --locked
uv sync --project agents --python 3.12 --all-extras --dev --locked
npm --prefix web ci
# Windows test commands; on Linux use .venv/bin/python:
api/.venv/Scripts/python.exe -m pytest api/tests -q
agents/.venv/Scripts/python.exe -m pytest agents/tests -q
cd web
npx vitest run
cd ..
```

Tests requiring disposable PostgreSQL or platform-specific facilities skip when unavailable; skips are not acceptance passes. [Foundation setup](FOUNDATION_SETUP.md) documents isolated local database initialization, migration and permission/recovery tests. Those services are a development fixture, not a second editor deployment. The repository CI additionally builds the web app, checks generated types, runs real database checks and validates Terraform.

Build the production images from the repository root on a compatible Docker host:

```bash
docker build -f deploy/production/api.Dockerfile -t trimbin-api:local .
docker build -f deploy/production/web.Dockerfile -t trimbin-web:local .
```

Building images alone does not configure or start the app. It needs PostgreSQL/ClickHouse, runtime credentials, initialized schemas, authorized media paths and all relevant workers. Do not treat `.env.example` dummy values as working credentials or use fixture inference for the cloud submission.

## Operator deployment prerequisites

The checked-in Terraform describes this account-specific AWS deployment. Existing certificate, WAF, CloudFront identity, GitHub OIDC provider and DNS are prerequisites, not resources that a different account can silently reuse. Adapt/import owned resources and domain configuration deliberately for another account; this is not a generic one-click customer installer. Use the existing protected remote state for this installation. See [deployment design](DEPLOYMENT_DESIGN.md).

Prepare one encrypted SSM Advanced SecureString named `/trimbin/runtime`. Its JSON envelope has three maps; values are protected strings:

| Map | Required purpose |
| --- | --- |
| `runtime` | Actual `TRIMBIN_` Settings variables for app/worker roles, database DSN, separate ClickHouse identities, signed sessions, owner/team access, models, media roots, limits and CORS |
| `bootstrap` | `TRIMBIN_BOOTSTRAP_DATABASE_URL` (postgres admin DSN) and `TRIMBIN_CLICKHOUSE_ADMIN_PASSWORD` |
| `files` | `postgres_admin`, `postgres_writer`, `clickhouse_admin`; passwords must agree with their matching DSNs/variables |

Use private JSON/environment files, never shell arguments or logs containing secret values. PostgreSQL hosts resolve as `postgres:5432` and ClickHouse as `clickhouse:8123` inside Compose. Processing paths are `/media/originals`, `/media/staging`, `/media/derived`, `/media/library` and `/media/exports`; allow only intended aliases and project mappings. Model cache is `/model-cache`. Set `cloud-poc`, `nebius`, the explicit live switch, current production catalogs and real Token Factory key for live operation. Configure the owner and roster instead of relying on development defaults. All supported settings and the deployment variable names are in [configuration](CONFIGURATION.md), [.env example](../.env.example) and [Settings source](../agents/trimbin_agents/config.py).

`configure.py` reads that SSM envelope, validates the encoding and produces private runtime/bootstrap/media files. It does not obtain partner credits or generate a valid provider key. Keep SSM credentials and private owner access protected separately from database backups.

For existing main-push automation, GitHub Variables must identify the deployment role, instance, registry, release bucket and CloudFront distribution. The role trust is restricted to this repository's main branch. Infrastructure is applied with Terraform by the operator; the release workflow checks/builds/publishes and rolls out images through SSM. It does not automatically apply arbitrary Terraform changes on every push.

The release script applies schema migrations/bootstrap, starts the canonical Compose services and checks readiness. Immutable release images are preferred; `TRIMBIN_LOCAL_BUILD=true` is the explicit operator preflight mode used with locally built images. Neither mode creates a second production workflow. The historical tag remains untouched.

## Routine health and recovery

`/api/ready` checks database readiness; `/projects` checks frontend delivery. A healthy endpoint does not prove every worker, model credit, quality gate or NLE import. Inspect actual job state and scoped output when diagnosing work. Never print full runtime environment or provider headers into logs.

Daily backup quiesces writers. Restore into separate compatible storage, run bootstrap to recreate access entities as well as schema, and verify source hashes/membership/revisions before traffic cutover. Image rollback does not roll back database schema. [Recovery evidence](AWS_CUTOVER.md) and [cost/retention assumptions](COST_ESTIMATE.md) explain the tested scope and storage growth.
