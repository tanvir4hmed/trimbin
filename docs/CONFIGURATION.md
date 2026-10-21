# Credentials and configuration plan

Phase 2 implements the shared API/agent registry, portable core settings, `.env.example` and safe per-service capability reports. Optional partner integrations and reserved local-model settings below remain future contracts. Existing editorial routes are not migrated by copying this environment; see [foundation setup](FOUNDATION_SETUP.md).

## Storage and access policy

Put secret values in GitHub Actions Secrets, preferably in the approved deployment environment, and ignored local configuration. Put ordinary settings in GitHub Variables and a documented `.env.example` containing placeholders only. Runtime containers receive a per-service subset through deployment secret injection. GitHub Secrets alone do not automatically deliver values to a running workstation or server. `NEXT_PUBLIC_*`, browser bundles, logs and Git commits must never carry private credentials.

GitHub lists secret names but does not expose existing values back to the client. A successful inventory is not evidence that a credential still works. Do not create dummy secrets to make a deployment check green. [GitHub secret documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

## Configuration registry and reserved extensions

| Name | Storage and requirement | Missing value behavior |
| --- | --- | --- |
| TRIMBIN_PROFILE | Variable; development or cloud-poc; future studio profile reserved, not delivered | Development defaults only; production must be explicit |
| TRIMBIN_INFERENCE_MODE | Variable; fixture or nebius; self-hosted endpoint extension deferred unless separately approved | Fixture permitted only in explicit development; no silent live fallback |
| TRIMBIN_NEBIUS_BASE_URL | Variable; account-selected documented API endpoint | Live preflight reports configuration missing |
| TRIMBIN_NEBIUS_API_KEY | Secret; required for live Nebius calls | Editing/export and credential-free checks continue; live analysis unavailable |
| TRIMBIN_VISION_MODEL | Variable; exact discovered model ID | No claim of live visual analysis |
| TRIMBIN_REASONING_MODEL | Variable; exact discovered model ID | Manual sequence and deterministic assembly remain available |
| TRIMBIN_ASR_MODEL | Variable; supported audio model/adapter | Transcript shown as unavailable; do not invent dialogue |
| TRIMBIN_EMBEDDING_MODEL | Variable; supported embedding adapter | Disable semantic path visibly; structured retrieval may continue |
| TRIMBIN_EMBEDDING_VERSION | Variable; model/index generation identifier | Prevent incompatible index activation |
| TRIMBIN_LOCAL_MODEL_BASE_URL | Variable; reserved for a future self-hosted model server, not required this release | Local inference unavailable; no paid failover without configuration |
| TRIMBIN_LOCAL_MODEL_API_KEY | Reserved secret only if a future self-hosted endpoint requires authentication | Local server auth check fails clearly |
| TRIMBIN_MEDIA_BACKEND | Variable; filesystem initially | Explicit startup configuration |
| TRIMBIN_ORIGINALS_ROOT | Local/host setting; allowed read-only root | Ingest/export preflight explains missing source root |
| TRIMBIN_PROXIES_ROOT | Local/host setting; writable derived cache | Proxy jobs blocked with useful error |
| TRIMBIN_EXPORT_ROOT | Local/host setting; writable output root | Export blocked before starting work |
| TRIMBIN_ALLOWED_MEDIA_ROOTS | Local/host setting; path whitelist | Deny unrestricted file access |
| TRIMBIN_DATABASE_URL | Secret when it contains operational database credentials | Integration runtime needs local PostgreSQL; unit tests use isolated doubles |
| TRIMBIN_CLICKHOUSE_HOST | Variable | Archive integration unavailable until local service is configured |
| TRIMBIN_CLICKHOUSE_PORT | Variable | Chosen with protocol rather than assumed cloud port |
| TRIMBIN_CLICKHOUSE_SECURE | Variable | Explicit HTTPS or private local HTTP decision |
| TRIMBIN_CLICKHOUSE_USER | Variable; least-privilege application writer | No use of an unrestricted admin as a hidden fallback |
| TRIMBIN_CLICKHOUSE_PASSWORD | Secret; newly generated self-hosted writer password | Local integration provisioned during approved setup |
| TRIMBIN_CLICKHOUSE_READER_USER | Variable; separate SELECT-only identity | Semantic/agent retrieval fails closed |
| TRIMBIN_CLICKHOUSE_READER_PASSWORD | Secret; newly generated reader password | No bypass through writer credentials |
| TRIMBIN_SESSION_SECRET | Secret; new stable signing key | No production session signing with a hardcoded fallback |
| TRIMBIN_DEMO_PASS | Secret; optional scoped judge/demo access | No default public editor/admin credential |
| TRIMBIN_CORS_ORIGINS | Variable | Explicit local or hosted origins |
| TRIMBIN_TAVILY_API_KEY | Secret; optional | Web research hidden/unavailable; footage workflow unaffected |
| LANGSMITH_API_KEY | Secret; optional | Tracing disabled; no application failure |
| LANGSMITH_PROJECT | Variable; optional | Use configured non-sensitive project label |
| LANGSMITH_TRACING | Variable; false by default | No external tracing |
| LANGSMITH_HIDE_INPUTS | Variable; true initially | Suppress private prompt/media contents from traces |
| LANGSMITH_HIDE_OUTPUTS | Variable; true initially | Suppress private outputs from traces |
| TOLOKA_API_KEY | Secret if a supported optional automation needs it | No labeling/training call; core build unaffected |
| TRIMBIN_DEPLOY_HOST | GitHub Variable; after host choice | Package artifacts only; no deployment attempt |
| TRIMBIN_DEPLOY_USER | GitHub Variable; if SSH rollout selected | Deployment preflight blocked |
| TRIMBIN_DEPLOY_SSH_PRIVATE_KEY | Environment Secret; only if SSH rollout selected | No connection attempt |
| TRIMBIN_DEPLOY_SSH_KNOWN_HOSTS | Verified environment configuration; if SSH selected | Reject unverifiable host, do not disable checking |

Tendem integration uses its supported account/connector authentication. Do not invent an API-key variable before verifying the selected integration. Nebius AI Cloud provisioning may require additional project/service-account credentials only if that deployment path is chosen; Token Factory inference does not imply those credentials exist. Prefer short-lived workload credentials where supported. GitHub's built-in GITHUB_TOKEN can publish packages with explicit permissions; a personal access token is not automatically required.

## Current inventory without secret values

- Repository and environment secret names were inspected through GitHub CLI on 20 October.
- The present repository has nine legacy secret names, no repository Variables, and a production environment with no environment-scoped secrets returned.
- No new model-provider secret names were present in that inventory. No secret values were retrieved or displayed.
- A Tavily credential file exists outside the Git checkout. It remains outside the archive and has not been read, copied into Git or authenticated in this planning step.
- The detailed retirement map lives only in the external local archive at `D:\NVIDIA\archive\2026-10-20` because it documents the previous environment. It is not the new public configuration contract.

## Cleanup sequence

1. Phase 1 adds all-main-push credential-free CI and preserves automatic deployment per owner instruction. See [deployment design](DEPLOYMENT_DESIGN.md) for Terraform ownership and current limitations.
2. Phase 2 creates one settings schema, `.env.example`, startup capability reporting and missing-key tests. Consolidate the API and agent configuration instead of maintaining divergent settings.
3. Generate self-hosted database/session secrets during approved setup and store available new credentials through GitHub Secrets. Local originals paths remain local settings, not public repository content.
4. Use provided credentials only for the intended provider; record validated names and expiry metadata without values. Missing optional accounts do not block core phases.
5. Migrate code and workflows to the new registry, verify an isolated runtime, and prove that old settings are no longer referenced.
6. During approved cutover, remove obsolete GitHub Variables/Secrets and obsolete infrastructure references. Configuration cleanup does not authorize destroying old cloud resources or rewriting Git history. Preserve a documented recovery path before retirement.

## Credit planning

Owner reports LangSmith 100 USD, Tavily 25 USD and Tendem 50 USD received. The separate Token Factory 25 USD email is still pending. Toloka 50 USD was not applied after its prefilled coupon errored during signup; support resolution is pending. These are separate offers, not a pooled budget. Expiry and account-specific feature coverage require confirmation. Live model evaluation should begin with a bounded approved sample and measured unit cost; additional paid runs or infrastructure require approved scope. Optional training, web research and external human evaluation are not core dependencies.

## Quality and deployment constraints

The current delivery is a cloud-hosted complete editorial PoC. Original/proxy/export roots, operational state and model endpoints are independently configurable to support future studio deployment. The cloud edition accepts staged/uploaded media; an actual local installation and hardware proof are outside scope. No mandatory proprietary paid LLM dependency is planned. Initial host sizing and ongoing hosting cost require an explicit deployment budget.

Open-model local serving can remove a model-provider per-token charge, but not workstation/power/storage/maintenance costs. An open model served through a paid API still incurs serving charges. Credits do not prove a model is deployable on the editor's machine, and exhaustion must not trigger a silent inferior model, sparse sampling, lower detail or proxy-based final render. Show a clear unavailable/budget state, preserve manual work and obtain approval for any new paid scope.

Cost/resource settings are subordinate to [quality gates](QUALITY_STRATEGY.md). Every model/precision/sampling configuration promoted for use needs its own evidence. Optional partner services may remain disabled, but their absence cannot be hidden behind a claim that live quality was verified. A future offline profile would need to disable all external integrations and pass no-network verification; that work does not block this cloud edition. Token Factory remains outside the application's private service network unless provider-supported private connectivity is actually established and verified.

## Phase 2 implementation evidence

API settings now re-export the agent package registry. Legacy defaults remain under the `legacy-cloud` profile while portable development/cloud profiles are explicit. TLS is configurable in both ClickHouse consumers. Local database/session credentials were generated under ignored `.secrets/foundation`; no values were printed or registered as production GitHub secrets. Two replaced configuration source files are preserved with hashes outside the repo in `D:\NVIDIA\archive\2026-10-21-phase2`. Actual provider keys and the production host/DSN remain pending; local test credentials are not a production deployment configuration.

## Phase 3 media settings

See [media setup](MEDIA_SETUP.md) for the implemented path and private configuration. `TRIMBIN_STAGING_ROOT` is required for controlled uploads; it must share a filesystem with uploaded originals. `TRIMBIN_MEDIA_ROOTS` maps aliases to operator-controlled mounted folders; `TRIMBIN_MEDIA_ROOT_PROJECTS` grants each alias to specific project IDs. Both use JSON. Mounted sources must also be inside `TRIMBIN_ALLOWED_MEDIA_ROOTS`.

`TRIMBIN_MEDIA_THREADS` defaults to 2, `TRIMBIN_MEDIA_WORK_BYTES` to 2 GiB per attempt, `TRIMBIN_MEDIA_RESERVE_BYTES` to 1 GiB and `TRIMBIN_MEDIA_TIMEOUT_SECONDS` to 3600 per encoding operation. Exceeding a limit fails visibly. `TRIMBIN_TEAM_PASSES` is a private sign-in setting; PostgreSQL membership additionally controls project permissions. No example credential authorizes a production user.

## Phase 4 placeholder and adapter configuration

The owner explicitly requested dummy values and testing later. `.env.example` and ignored `.secrets/inference/runtime.env` now contain nonfunctional `DUMMY_...` provider/model examples. Real database/session/legacy values are not overwritten. Placeholders never satisfy live preflight and are not registered as working GitHub Secrets. See [adapter setup](INFERENCE_SETUP.md).

New variables: `TRIMBIN_INFERENCE_LIVE_ENABLED=false`, `TRIMBIN_INFERENCE_CATALOG_PATH`, `TRIMBIN_INFERENCE_TIMEOUT_SECONDS=120`, `TRIMBIN_INFERENCE_MAX_RETRIES=1` (maximum 2), `TRIMBIN_INFERENCE_MAX_OUTPUT_TOKENS=8192`, `TRIMBIN_INFERENCE_TEMPERATURE=0`, and `TRIMBIN_INFERENCE_RESPONSE_BYTES=8388608`. These are bounded development defaults, not approved model-quality settings. Live CLI work also requires `--live`; do not run it until credits, rights and sample scope are ready. Model profiles require verified modalities and exact account IDs before use.

No new runtime provider dependency is required for Phase 4: the API's existing aiohttp transport handles the documented endpoints. Optional partner tokens are placeholders only; no Tavily, LangSmith, Toloka or Tendem call is activated. Speech is explicitly unavailable until its supported provider/adapter is established.
