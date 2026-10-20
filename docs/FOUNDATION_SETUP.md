# Portable foundation setup and recovery

Implemented in Phase 2, 21 October 2026. This provides configuration, database services and operational interfaces. Existing editorial routes still use the previous cloud storage/state integrations until their migration phases. Selecting a new profile does not migrate data or deploy the completed editor.

## Requirements and versions

Use Python 3.12 and uv, Docker Engine/Desktop with Compose v2, and enough free disk for database files plus a complete cold backup. On Windows, Docker needs a working Linux-container backend. This development PC has neither Docker nor WSL, so container lifecycle verification runs in the added GitHub CI job rather than being claimed as locally tested.

PostgreSQL 17 and ClickHouse 26.8 LTS are pinned by registry digest in [Compose](../deploy/foundation/compose.yaml); Python dependencies are resolved in the API and agent `uv.lock` files. ClickHouse needs the current text/vector index support used by the retained evidence migrations. Text indexes became production-ready in 26.2; [26.8 is an LTS release](https://clickhouse.com/blog/clickHouse-release-26-08). Updating a digest requires rerunning schema, isolation and restore checks.

## Local setup

Run from the checkout root:

```powershell
uv sync --project api --python 3.12 --all-extras --dev --locked
api/.venv/Scripts/python.exe tools/foundation.py init
api/.venv/Scripts/python.exe tools/foundation.py config
api/.venv/Scripts/python.exe tools/foundation.py up
api/.venv/Scripts/python.exe tools/foundation.py migrate
api/.venv/Scripts/python.exe tools/foundation.py check
```

On Linux replace `api/.venv/Scripts/python.exe` with `api/.venv/bin/python`. No Nebius/Tavily/LangSmith/Toloka/Tendem credential is needed for these commands. No provider call is made.

`init` creates fresh random credentials and a development runtime environment under ignored `.secrets/foundation`. It refuses to overwrite existing credentials. `.foundation-data` holds persistent PostgreSQL and ClickHouse data. Keep these directories private and out of images, artifacts and Git. Compose secret mounts are file mounts, not an encrypted external secret vault; protect the host and backup storage. [Docker secret model](https://docs.docker.com/compose/intro/compose-application-model/).

Ports 5432 and 8123 bind to host loopback only. Database containers share an internal network. The lifecycle tools use these default ports; leave them unchanged when using those tools. No public database port or cloud resource is created by local setup.

The PostgreSQL admin applies migrations; `trimbin_writer` has DML rights, not schema ownership. ClickHouse has a separate admin, SELECT/INSERT application writer and the existing SELECT-only retrieval role. Maintenance/DDL must use a dedicated administrative operation, never reader credentials. `check` verifies connectivity and actual denied DDL/write operations; arbitrary network failures do not count as a passing permission test.

## Configuration and interfaces

API and agents now import the same Settings registry in `agents/trimbin_agents/config.py`. `legacy-cloud` preserves existing deployed defaults; `development` and `cloud-poc` explicitly identify portable configuration. Cloud PoC rejects fixture inference. Secrets are excluded from settings repr/dumps. ClickHouse TLS and port are configurable in both API and MCP paths.

The generated environment has no default model IDs for the portable inference path. Capability reports distinguish missing configuration, fixture-only behavior and configured-but-unverified capabilities. They do not certify provider access, model quality or migrated API routes.

```powershell
cd api
.venv/Scripts/python.exe -m app.foundation.capabilities --service api --env-file ../.secrets/foundation/runtime.env
```

Supported preflight service groups are API, worker, retrieval and inference. Media roots remain unset until Phase 3. Optional integrations are absent without credentials; manual foundation work does not depend on them. Provider/production credentials have not been registered from local test secrets. Do not copy a localhost development DSN into production GitHub Secrets.

`PostgresRepository` provides transactionally consistent state revisions, immutable version rows through its interface, command receipts and outbox records. Commands are project/actor scoped; a changed body under the same key conflicts. Caller authorization is required before invoking the repository; these primitives are not a public authentication boundary.

`PostgresJobs` provides idempotent enqueue, transactional claim, lease renewal, expiry recovery, cancellation, bounded retries and fenced completion. Completion returning true means the current lease's result was accepted; a cancellation may make the resulting state cancelled rather than succeeded. Outbox delivery is at least once; Phase 5 consumers must deduplicate event IDs and preserve generation ordering. PostgreSQL locking follows [transaction-scoped advisory locks and row locks](https://www.postgresql.org/docs/17/explicit-locking.html).

The checksum-protected `schema.sql` is migration version 1. Never edit an applied migration in place; later phases add numbered migrations and corresponding ledger handling. Legacy Firestore readers are deliberately not switched in Phase 2.

## Backup and restore

Quiesce application writers first. The supplied backup stops both data services, archives their data together, writes a SHA256 checksum and restarts the services. This is a downtime-based cold snapshot, not online point-in-time recovery. Save matching private credentials separately in protected storage; database snapshots contain private data and credential hashes.

```powershell
api/.venv/Scripts/python.exe tools/foundation.py backup --directory D:/private-backups/foundation-001
```

Restore only a trusted operator-created backup, with matching image digests and credentials, into an empty data directory. The helper refuses to delete or overwrite existing data and checks checksum/archive paths before extraction:

```powershell
api/.venv/Scripts/python.exe tools/foundation.py restore --directory D:/private-backups/foundation-001
api/.venv/Scripts/python.exe tools/foundation.py check
```

Preserve/move the existing data directory deliberately before restore; never use routine `down -v` as a migration or recovery step. Recheck saved revisions, evidence counts and source references before reopening writers. CI performs this rehearsal with disposable records and verifies both stores after restart and restore.

Changing a password file is not database password rotation. PostgreSQL initialization runs only on an empty data directory. Rotate database roles and consumers together through a separate operation, then verify access and backups. Cloud bootstrap refuses a changed credential manifest against its persistent private directory.

## Terraform target and package

[Portable Terraform](../infra/envs/portable) is an isolated environment with its own state prefix. It declares a fixed host, private subnet, data disk, service account and scoped artifact/secret access. The host uses external egress for installation; only IAP SSH ingress is allowed. HTTPS/editor deployment belongs to later cutover work. There is no Kubernetes or autoscaling.

The data disk has `prevent_destroy`, and the VM has deletion protection. Boot image, package object and SHA256 are explicit inputs. Secret values never enter Terraform variables/state: bootstrap retrieves an existing Secret Manager JSON object through VM identity. Required secret keys are `postgres_admin`, `postgres_writer`, `clickhouse_admin`, `clickhouse_writer`, `clickhouse_reader`, `session_secret`; use the generated 64-character hex values.

After staging/committing the desired source, `python tools/package_foundation.py` packages Git-tracked source only into ignored `.secrets/artifacts`. It does not upload anything. An approved operator publishes the immutable artifact, provides the matching hash/secret resource and initializes a separate backend before any apply. The bootstrap starts database containers; run migrations using the supplied Python environment before allowing application consumers. No image switch or production migration is hidden in host creation.

Terraform validation was run without a backend. No apply, new paid host, remote secret deletion or legacy-resource destruction was performed. Existing push-triggered deployment stays active. The current app's imperative image rollout remains unchanged until the migration/cutover phase; the new infrastructure target is Terraform-owned.

## Verification status

Local configuration/unit and existing regression tests are recorded in [phase status](PHASE_STATUS.md). The GitHub `Portable database foundation` job starts the pinned services, applies migrations, checks permissions, runs concurrent revision/replay/lease tests, restarts the stores and restores a cold backup.

Docker-based acceptance remains unverified on this PC. Do not interpret skipped PostgreSQL tests as passed, or a pushed commit as a successful deployment. Per owner instruction, deployment completion is not polled.
