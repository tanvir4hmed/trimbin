# Configuration

The deployed application has one configuration registry in `trimbin_agents.config.Settings`, re-exported by the API. Profiles are `development` and `cloud-poc`; they select safeguards, not different applications. Cloud PoC refuses fixture inference. Production is configured through encrypted AWS SSM `/trimbin/runtime`, read by `deploy/production/configure.py`. Local examples contain placeholders only.

| Configuration | Location and purpose |
| --- | --- |
| Token Factory API key | GitHub secret `TRIMBIN_NEBIUS_API_KEY` and encrypted SSM runtime; only inference-capable services receive it |
| Database passwords, signing key, team passwords | Generated private SSM configuration and ignored operator files; excluded from logs, images and Git |
| Owner login | Operator's ignored `.secrets/aws/access.json`; email/password sign-in, secure HttpOnly playback cookie plus session token |
| Deployment role / instance / registry / release bucket / distribution | GitHub Variables `TRIMBIN_AWS_DEPLOY_ROLE`, `TRIMBIN_AWS_INSTANCE_ID`, `TRIMBIN_ECR_REGISTRY`, `TRIMBIN_RELEASE_BUCKET`, `TRIMBIN_CLOUDFRONT_DISTRIBUTION` |
| AWS deployment authentication | GitHub OIDC restricted to this repository's main branch; no stored AWS access key in the workflow |
| Source storage | `/srv/trimbin/media/{originals,staging,derived,library,exports}` on encrypted EBS; staging and originals share one container mount for atomic promotion |
| Model cache | `/srv/trimbin/model-cache`; Whisper and Hugging Face caches stay writable without making container roots writable |
| Model identities | `config/model-profiles.production.json` and `config/embedding-identity.production.json`, versioned without secrets |

Runtime selects `nvidia/Nemotron-3.5-Super-VL`, `nvidia/nemotron-3-super-120b-a12b`, `Qwen/Qwen3-Embedding-8B` (768 dimensions, L2) and CPU `Systran/faster-whisper-large-v3` int8. Public aliases do not pin a weight revision or disclose provider precision. The tested vision endpoint accepts eight images per request. Larger frame sets are batched without dropping frames; validated batch observations are combined by the reasoning model. Exact quality remains subject to paired evaluation.

Settings include source/derivative/export roots, per-project mounted-library access, upload bounds, scratch reserve/limit, FFmpeg thread/timeout bounds, worker leases, live inference switch, model/time/token/response limits and CORS origins. Only named roots and project-authorized relative paths are accepted. An arbitrary folder on a browser user's PC is not a path the cloud server can read.

Optional Tavily, LangSmith, Toloka and Tendem are not required by this workflow and are not presented as active integrations. Their credits do not pay for AWS hosting. Browser fonts currently use Google's font CDN; Google OAuth remains an optional identity mechanism only. There are no Google Cloud application SDKs, GCP deployment workflows, managed ClickHouse credentials or remote document/object-store dependencies in the canonical runtime.

Nine obsolete GCP/managed ClickHouse repository secrets were removed during cutover. The new workflow reads runtime secrets on the host from SSM; listing a GitHub secret name does not reveal or validate its value. Terraform state is encrypted and private but must still be treated as potentially sensitive. Never commit state, private environment files, generated configuration or original footage.

Changing model identity/dimension/precision/normalization requires a new compatible index generation and quality review. Do not mix old vectors with Qwen vectors merely because dimensions match. Missing provider credentials make live inference unavailable; they never select fixture output silently. Manual editing and rendering an already approved timeline do not require a paid model call.
