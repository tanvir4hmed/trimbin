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

Supported preflight service groups are API, worker, retrieval and inference. Configure Phase 3 media roots as described in [media setup](MEDIA_SETUP.md). Optional integrations are absent without credentials; manual foundation work does not depend on them. Provider/production credentials have not been registered from local test secrets. Do not copy a localhost development DSN into production GitHub Secrets.

`PostgresRepository` provides transactionally consistent state revisions, immutable version rows through its interface, command receipts and outbox records. Commands are project/actor scoped; a changed body under the same key conflicts. Caller authorization is required before invoking the repository; these primitives are not a public authentication boundary.

`PostgresJobs` provides idempotent enqueue, transactional claim, lease renewal, expiry recovery, cancellation, bounded retries and fenced completion. Completion returning true means the current lease's result was accepted; a cancellation may make the resulting state cancelled rather than succeeded. Outbox delivery is at least once; Phase 5 consumers must deduplicate event IDs and preserve generation ordering. PostgreSQL locking follows [transaction-scoped advisory locks and row locks](https://www.postgresql.org/docs/17/explicit-locking.html).

The checksum-protected `schema.sql` is migration version 1. Never edit an applied migration in place; numbered migrations now extend it; version 2 adds media sources, uploads and project membership. Legacy Firestore readers are deliberately not switched in Phase 2.

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

Changing a password file is not database password rotation. PostgreSQL initialization runs only on an empty data directory. Rotate database roles and consumers together through a separate operation, then verify access and backups.

## Package and hosting boundary

The unapplied Phase 2 GCP host draft was an incorrect hosting assumption. Its five tracked files were moved, with verified hashes, outside Git to `D:\NVIDIA\archive\2026-10-21-phase3-gcp-draft`. No live resource or Terraform state was changed. No new GCP hosting requirement is introduced.

The foundation and [media package](MEDIA_SETUP.md) define provider-neutral services and volumes. A new host/provider and budget remain undecided; eventual new infrastructure must be Terraform-managed. Existing push-triggered deployment stays active until approved cutover.

After staging/committing source, `python tools/package_foundation.py` packages Git-tracked source into ignored `.secrets/artifacts`. It does not upload or provision anything. Apply migrations before allowing application consumers. The package alone does not deploy the completed editor.

## Verification status

Local configuration/unit and existing regression tests are recorded in [phase status](PHASE_STATUS.md). The GitHub `Portable database foundation` job starts the pinned services, applies migrations, checks permissions, runs concurrent revision/replay/lease tests, restarts the stores and restores a cold backup.

Docker-based acceptance remains unverified on this PC. Do not interpret skipped PostgreSQL tests as passed, or a pushed commit as a successful deployment. Per owner instruction, deployment completion is not polled.
