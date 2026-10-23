# Complete workflow package and acceptance

Phase 9 implementation, 23 October 2026. Runtime tests remain deferred by owner instruction. This page describes the runnable package and required rehearsal; it is not evidence that a clean deployment, live quality comparison or complete workflow has passed. No paid host is provisioned or chosen here.

## Editor entry and authority

Open `/studio`, sign in with an operator-issued team account, and choose a PostgreSQL project. The new shell links Media → Evidence & selections → Timeline & exports, without querying the legacy project/dashboard APIs. The status view shows persisted source counts, timeline revisions and job states. Completion counts do not certify model quality or final-file fidelity.

Use [media project bootstrap](../tools/media_project.py) to grant each exact account owner/editor/viewer membership. Team-pass authentication is reused; use strong distinct per-account codes and a 32+ character session signing secret. Do not grant private membership to a shared guest-pass identity: shared handles are not individual authentication. Password rotation does not revoke already-issued sessions; rotate signing secret to invalidate all sessions when necessary. No credential is embedded in frontend build arguments. TLS is required before exposing sign-in beyond loopback.

The portable API entrypoint `app.portable:app` mounts auth, workflow, media, inference, evidence, timelines and both export routes. Legacy operational endpoints are absent. Existing legacy code/SDK packages remain in the source and dependency lock until Phase 10's retirement audit; that is not a requirement for GCP infrastructure or credentials on this workflow. OAuth is optional; password sign-in works without it. `/health` is process liveness only, not database, worker or model readiness.

## Build the package

Use Python 3.12 and the repository's locked API environment for operator tools. Package a committed source revision:

```powershell
api/.venv/Scripts/python.exe tools/package_portable.py --ref HEAD --output .secrets/artifacts/portable.tar.gz
```

The new packager reads immutable Git blobs rather than local working files. It includes API, agents, frontend, lockfiles, SQL, deployment files, docs, tools and license, plus a per-file SHA256 manifest and archive checksum. It excludes local secrets, media, dependencies, archives and symlinks. Existing output is not overwritten. Historical Terraform and evaluation/workflow source is retained for provenance and documentation links; it is not an instruction to apply the old cloud stack. Review committed source for secrets before release; a filename allowlist is not a content secret scanner. The older foundation packager remains for its existing caller; use this new tool for the complete application.

Extract into a fresh controlled directory and verify the checksum/file manifest. Build from that source with operator-approved immutable base image references; replace the placeholder arguments below with actual digests. No registry or build was invoked in this phase.

```sh
docker build -f deploy/portable/api.Dockerfile --build-arg PYTHON_IMAGE=<python-3.12-slim-digest> --build-arg UV_IMAGE=<compatible-uv-image-digest> -t <api-build-tag> .
docker build -f web/portable.Dockerfile --build-arg NODE_IMAGE=<node-22-slim-digest> -t <web-build-tag> web
```

API dependency installation uses `uv sync --locked`; frontend uses `npm ci`. Image builds still install the distribution's FFmpeg package, so source/lock reproducibility does not mean byte-identical images across time. Record the resulting image digests, OS/FFmpeg versions, available encoders, build arguments and architecture in the evidence record. Deploy those built image digests. Image pinning and dependency installation are not substitutes for vulnerability triage or codec/license checks.

## Configure and start on an approved disposable host

1. Initialize, start and migrate the pinned foundation services with [foundation setup](FOUNDATION_SETUP.md). Do not reuse production data for a destructive rehearsal. The foundation helpers currently assume loopback database ports 5432/8123; changed endpoint rehearsals must account for this operator-tool limitation.
2. Copy [Compose placeholders](../deploy/portable/compose.example.txt) to a private ignored file. Supply the tested API/frontend/nginx image digests, runtime env path and absolute volume paths. All new cloud host provisioning remains Terraform-managed; these manifests create containers only.
3. Create the mounted directories before startup. The portable application image runs as UID/GID 10001; grant writable upload/staging, derived and export directories accordingly. Workers see originals/library read-only. Keep originals, staging, derived, library and exports disjoint as required by MediaPaths. Preserve private file permissions for env/model configuration. Do not recursively change ownership of an existing customer media tree.
4. In the container env, configure PostgreSQL at `postgres:5432`, ClickHouse at `clickhouse:8123` with secure=false for this private network, and the existing least-privilege writer/reader credentials. Use container roots `/media/upload-store/originals`, `/media/upload-store/staging`, `/media/derived`, `/media/library`, `/media/exports`; set allowed roots and project root grants explicitly. Set the catalog path to a private file under `/model-config` when using live inference.
5. For credential-free preparation use profile `development`, inference mode `fixture`, live-enabled=false. Fixture mode abstains and does not prove real analysis. `cloud-poc` with fixture mode is rejected. Live acceptance requires explicit Nemotron model profiles, Token Factory access and approved live-call scope; configure per [inference setup](INFERENCE_SETUP.md). Speech support and held-out quality remain open gates.
6. Set a real session secret and unique team passes privately; register the matching PostgreSQL membership with the operator tool using a host-accessible database env. Do not commit that env or use literal placeholder secrets for sign-in.
7. Start the combined package from the extracted root:

```sh
docker compose --env-file /absolute/private/compose.env -f deploy/media/compose.yaml -f deploy/portable/compose.yaml up -d
```

The overlay adds the frontend and gateway and switches only its API process to the portable entrypoint. It retains the foundation external network and distinct media, analysis, projection, editable export and render workers. It does not alter the existing automatic deployment workflows. Foundation must already be running and migrated. Point the browser at loopback port 8088 (or configured port); `/` redirects to `/studio`. The original API loopback port 8080 remains available for operator debugging.

The gateway strips `/api`, streams upload/download bodies, forwards authorization/ranges and refreshes Docker service DNS. Access logs are disabled to avoid routine signed-ticket logging; inspect all upstream/error logging policies before public exposure. Upload requests remain bounded to the existing 8 MiB chunk protocol; do not send whole movie bodies through a single request. External HTTPS ingress, rate limiting and public judge access are Phase 10 cutover work. API/analysis have configured provider egress; fonts in the existing root layout also use Google's font CDN. This is not an air-gapped package.

The overlay currently uses one private env file across application services, as the earlier media manifest does. That means workers can receive credentials they do not need. Per-service secret minimization is a cutover hardening gate, not a completed property of this rehearsal package.

## Rehearsal and evidence

Create a private pending register; this performs no runtime checks:

```sh
python tools/workflow_acceptance.py init .secrets/acceptance/run-001.json
```

Record the commit, source-corpus manifest SHA256, host description, image digests and full model identity. Every gate begins pending. Run the following on cleared footage only when runtime testing resumes:

| Gate | Required observation |
| --- | --- |
| Ingest integrity | Interrupted upload/resume, mounted originals, stable source IDs and unchanged hashes |
| Real analysis | Actual Nemotron/Token Factory run with request/config provenance; no fixture substitution |
| Review/retrieval | Corrections and selections persist; stale/missing indexes fail; queries stay in project |
| Timeline persistence | Saved revisions, repeated clips, stale writes and restore survive worker/API restart |
| Both exports | Actual Premiere relink/frame/audio check and independent original-to-MP4 fidelity check |
| Isolation | Anonymous/outsider/viewer write denial; project-scoped tickets and artifacts |
| Recovery | Cancel/hash/decode/encode, lease expiry, retry, disk exhaustion and interrupted download |
| Portability | New physical media roots and service aliases/addresses, same logical aliases/IDs, saved work usable |
| Restore | Quiesced matching PostgreSQL/ClickHouse/media/export snapshots restored into new empty paths |
| Quality | Frozen held-out corpus and actual paid-model baseline, editor review, no critical regression |
| Resources | Corpus bytes/duration, elapsed time, peak container memory and scratch, inference bytes/cost |

For remapping, stop writers and workers, snapshot both databases plus original/derived/export volumes and private config separately, restore into fresh paths, change host bind paths without changing logical root aliases, then verify content hashes and persisted revision IDs. Change database service aliases and runtime DSN/ClickHouse host together for the endpoint rehearsal; the supplied Compose defaults use fixed aliases, so record the exact rehearsal override. Never use `down -v` or erase the original snapshot as part of normal testing. Database-only backup is not footage recovery.

Capture `docker stats --no-stream` repeatedly during the run and use an independent host sampler for scratch peak and elapsed time. A single idle snapshot is not a peak measurement. Keep raw reports private and record units/intervals; do not infer large-movie throughput from short fixtures. Render scratch is especially large; see [render limits](RENDER_SETUP.md).

Attach operator-reviewed evidence files to each gate as `{ "path": "relative/report.json", "sha256": "...", "fixture_only": false }`, set its status to passed only after the actual check, and retain failure notes. `python tools/workflow_acceptance.py check <record>` checks required metadata and local evidence hashes, rejecting missing/fixture evidence. It does not inspect the truth of a report or approve release by itself. Evidence must never be committed if it contains private footage, credentials or customer details.

Phase 9 runtime acceptance remains pending until these observations exist. Phase 10 cutover, secret retirement, publication and judging access require the next approval. Future workstation GPU sizing, local-only inference, offline operation and terabyte performance remain outside current claims.
