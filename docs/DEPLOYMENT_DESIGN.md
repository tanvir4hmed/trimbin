# Terraform and continuous deployment design

Phase 1 decision, 20 October 2026: the owner explicitly requested that pushes continue to deploy automatically and that work stop after pushing, without waiting for deployment. This supersedes earlier planning text proposing deployment-disabled migration.

## Legacy pipeline configuration

CI is configured for every push and pull request, including documentation-only main commits. Backend deployment calls the same CI as a required gate. Separate concurrency groups prevent a standalone run from cancelling the backend's reusable gate. Some checks run twice on backend-changing pushes; this is intentional until a later unified pipeline can preserve equivalent gates.

Backend deploy is configured to trigger on main changes to API, agents, ClickHouse, infrastructure and its workflow. Web deploy is configured to trigger on main web/workflow changes and has its existing web checks. Documentation-only changes do not necessarily redeploy either service. GitHub currently reports both deployment workflows as manually disabled. Destroy stays manual with typed confirmation; it is never invoked by normal push.

If re-enabled, the old deployment workflows operate the existing GCP runtime. Do not re-enable them as part of the new cutover. Push success is not deployment success. The replacement workflow belongs to Phase 10, and its successful rollout must be verified as a cutover gate.

## Terraform ownership

All new host/network/firewall/disk/IAM/registry/secret-resource infrastructure must be declared in Terraform. Use a remote locked state backend, separate environments, reproducible provider versions, explicit outputs and no credentials in committed variable files. Sensitive Terraform values can still enter state, so state requires restricted access and encryption.

The current GCP code provisions infrastructure through Terraform but ignores container image changes and rolls images/worker command out through `gcloud run deploy`. This is a documented transitional gap, not a claim of full Terraform deployment ownership. Replacing that ownership while replacing the runtime belongs to the approved foundation/cutover work; Phase 1 keeps the requested working deployment path.

Target: Terraform provisions the fixed cloud host and persistent disks/network; a versioned portable service manifest defines API, worker, PostgreSQL, ClickHouse and gateway workloads. Terraform-managed bootstrap/rollout configuration references an immutable application artifact. Compose is the host workload runner, not an alternative cloud provisioning system. Avoid managing the same setting independently in both Terraform and imperative cloud commands.

Build/push immutable images before the runtime rollout step. Bootstrap registry/state creation is distinct from application rollout, avoiding placeholder-image circular dependencies. Pin image digests and record release manifests. Preserve persistent volume identity when updating application containers. No automatic teardown/recreate of data disks on release.

## Network and secrets

```mermaid
flowchart TD
  Git[Approved main push] --> Checks[Credential-free CI]
  Checks --> Images[Build immutable images]
  Images --> TF[Terraform provision or update approved environment]
  TF --> Host[Fixed host and persistent disks]
  Host --> Services[Gateway API workers PostgreSQL ClickHouse]
  Secrets[Scoped secret injection] --> Services
  Services --> External[Explicit Token Factory egress]
```

Only authenticated HTTPS ingress is public in the target. Databases and workers use private service networking. Originals, derived caches, exports and databases have separate persistent paths and access rules. Token Factory is outbound external traffic. Future studio deployment can reuse the package but needs its own hardware/license/network validation.

Use existing short-lived workload federation where supported. GitHub Secrets hold secret values; Variables hold nonsecret settings. Never put credentials in user data, public browser configuration or logged Terraform outputs. Missing optional inference keys do not fail credential-free checks; a live analysis capability must fail visibly until configured.

## Cutover and recovery gates

Phase 2 supplies service/configuration definitions and Terraform design implementation without silently buying a new host. Actual resource creation requires an approved host/budget. Later phases move data and runtime consumers incrementally. Before cutover: back up, validate restore, prove source/revision integrity, rehearse the deployment and document which old image/schema remains compatible.

Rollback uses recorded compatible image/schema versions and preserved data; a code revert alone cannot undo a destructive migration. Do not delete old services, secrets or data before consumer and rollback audits. No new paid host, resource destruction, live model call or production-data migration occurs in Phase 1.

## Phase 3 hosting correction

GCP is not the new target or a requirement. The unapplied Phase 2 GCP host draft was archived outside Git with its hashes; no resources were changed. The [media Compose package](../deploy/media/compose.yaml) attaches API/worker to the foundation network, separates source/derivative mounts and declares process resource limits. It creates no host. Provider selection, Terraform provisioning, HTTPS and complete workflow cutover remain later approved work. The legacy deployment files remain in the repository but GitHub currently has both deployment workflows manually disabled. Pushing Phase 3 did not configure its new storage paths or PostgreSQL membership.

## 23 October 2026: current deployment status and revised phase boundary

GitHub Actions reports the backend and web deployment workflows as manually disabled. A push to `main` therefore does not currently deploy the app, regardless of triggers in the workflow files. Do not enable those old GCP workflows: they still provision or deploy the legacy runtime. Phase 10 will produce one replacement deployment workflow for the unified application, after its target, credentials and budget are selected. Phase 11 is reserved for the demo and submission after that cutover passes acceptance.

The accessible GCP project `trimbin` is marked `DELETE_REQUESTED` and billing is disabled. The available Cloud Asset Inventory query found no application Cloud Run services, VMs, GCS buckets or load balancer there, but the project is deleting and some direct queries failed. Another active project could not be fully inventoried with the current permissions. Managed ClickHouse Cloud was not inspected. These observations do not prove that all old data is gone or recoverable.

Phase 10 begins with read-only inventory of the ClickHouse organization/service, Terraform state and backups, and all reachable project/media stores. No destructive action or cutover proceeds until a restorable source is identified and its records/files are reconciled. If the source cannot be recovered, stop and record the exact data-loss decision before rebuilding from any remaining local archive. The replacement is one canonical application/runtime/configuration; the Phase 9 portable overlay is a rehearsal artifact and will not ship as a parallel product.
