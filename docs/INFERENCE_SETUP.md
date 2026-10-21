# Model adapters and deferred evaluation

Phase 4 implements an operator-facing inference layer in [app/inference](../api/app/inference), configuration placeholders, model discovery, grounded chat/image contracts, embedding generation identities and paired evaluation tools. The owner requested implementation now and testing later. No provider account, model quality, original-frame preparation or end-to-end inference workflow has been validated in this phase.

## Configuration now

[Environment example](../.env.example) and the ignored `.secrets/inference/runtime.env` contain unmistakable `DUMMY_...` values. The live switch defaults to false. A placeholder never satisfies provider preflight and is not registered as a working GitHub Secret. Existing real/legacy credentials are not overwritten. Optional partner placeholders enable no integration. Tendem authentication remains undecided rather than inventing a token format.

Run commands below from `api/` with its Python environment. On Windows use `.venv/Scripts/python.exe`; on Linux use `.venv/bin/python`. Output files go into ignored `.secrets/inference`; do not publish private prompts, footage, reports or the blind-review key. Windows directory ACLs remain the operator's responsibility; POSIX permissions alone do not configure them.

```powershell
.venv/Scripts/python.exe -m app.inference.cli --env-file ../.secrets/inference/runtime.env run --request ../config/inference-request.example.json --fixture ../config/inference-fixture.example.json
```

This is a prepared command for later testing, not an executed result. It validates an explicit synthetic answer and labels the artifact `fixture`. It makes no network call and is not simulated evidence about real footage. The fixture must match the complete normalized request fingerprint, including project scope. `fingerprint --request <path>` helps prepare a different deliberate fixture. Never use fixture output as a historical paid-model baseline.

## Activating live work later

1. Obtain the real Token Factory key; put it in ignored runtime configuration and the approved GitHub Actions Secret when deployment is configured. Set `TRIMBIN_INFERENCE_MODE=nebius` and `TRIMBIN_INFERENCE_LIVE_ENABLED=true` deliberately. The CLI also requires `--live`. No credit is spent during this implementation.
2. Run `discover --live`. It records the account's returned model IDs privately. Discovery is not proof of supported modalities, pricing, license approval or comparative quality.
3. Copy [model profiles](../config/model-profiles.example.json) privately and replace placeholder IDs. Set `TRIMBIN_INFERENCE_CATALOG_PATH` to that copy and select exact reasoning/vision/embedding IDs in configuration. Verify each task's model card, license, modalities, context/image limits and JSON behavior. Track exact revision when published; otherwise retain `unknown`/`unverified` and change `deployment_generation` whenever serving configuration changes. An alias cannot prove immutable weights or precision.
4. Use a meaningful account-accessible NVIDIA Nemotron candidate for source-grounded reasoning. Select current quality-passing models after discovery and evaluation; this phase does not falsely designate a latest/best model without access or results. Text models do not gain vision/audio ability from their name. Requests with frames use the vision profile; text-evidence comparison/draft tasks use the reasoning profile.
5. Prepare a cleared, bounded request and hashed original-detail frames. `run --request <private.json> --asset-root <private-frame-folder> --live` verifies source IDs, original hashes and durations against the Phase 3 PostgreSQL registry before transmission. Native source timebase is converted to integer microseconds only for analysis; final timeline/export still uses the canonical rational/frame contract.

The CLI is an operator tool with filesystem/database privileges, not a browser API. Assets use SHA256 filenames with `.png` or `.jpg`; remote URLs and arbitrary caller paths are not accepted. The operator supplies actual source-relative frame timestamps and the preprocessing recipe. Hash checking proves file identity, not that a frame really came from the declared time; automatic frame extraction and full-window orchestration remain integration work in Phase 5. Do not claim complete video coverage from a set of still frames.

The current transport accepts only the documented global Token Factory HTTPS endpoint, rejects redirects and does not inherit proxy credentials from the process environment. A future self-hosted adapter must implement the same task/output contract and its own endpoint/network policy; local serving is not delivered here. Raw video and speech endpoints are not guessed. Speech returns `speech_adapter_unavailable` until an appropriate actual audio-serving path is selected and implemented; text/image reasoning never invents transcripts.

## Transport and result behavior

Requests use `store=false`, bounded output tokens, configurable timeout and at most two configured retries. HTTP authentication, quota/rate limit, connection, timeout, provider rejection, refusal, truncated output and invalid grounded output have separate codes. Rate and quota share HTTP 429 and cannot reliably be separated without depending on provider-specific error bodies. Retried attempts remain visible with individual latency and reported token counts. A timeout may still have consumed provider tokens. Missing usage and cost stay null; estimates are not fabricated. Raw provider error text and keys are not logged.

The adapter supports explicit `json_object` and `json_schema` profiles. It always validates locally, including extra fields, source IDs, permitted intervals, candidate IDs and evidence citations. Slate labels must be in the allowed vocabulary. Missing evidence leads to abstention; invalid/partial output is not accepted. Retries repeat the bounded request; no silent model switch, old-cache replay, or automatic creative edit occurs. Model results remain proposals requiring editor approval.

Each run records input hash, source/evidence/brief/recipe identity, full model profile, prompt/schema/adapter versions, parameters, output validation, attempts and payload-byte counts. Payload counts describe attempted content rather than a network-meter measurement. The content-based generation includes project and provider context. Fixture generations are separate. This phase does not add a persistent cache or publish analysis into editorial state; Phase 5 will use these identities for atomic generation publication. Raw successful responses are hashed but not retained by default; private normalized results and usage are retained. Add rights-cleared raw capture deliberately if a later evaluation needs it.

## Embeddings

`embed --identity <private.json> --texts <private-json-array> --project <id> --live` uses the configured catalog. [Identity template](../config/embedding-identity.example.json) includes model, revision, precision, deployment generation, dimensions, normalization, preprocessing and index generation. The dimension value in the dummy template is illustrative, not a model choice. Actual response dimensions, finite numbers and batch indices are checked. Normalization is explicit. Corpus/query identities must match exactly via `require_compatible`; equal vector length alone is insufficient. Index writes and generation switching belong to Phase 5. The operator must supply only project-authorized text and use the declared preprocessing for both corpus and query.

## Quality work prepared for later

[Manifest](../config/evaluation-manifest.example.json) and [scores](../config/evaluation-scores.example.json) are synthetic format examples. Copy them privately and replace them with cleared footage cases, independent annotations, actual historical baseline runs, candidate runs and frozen metric definitions. `freeze --manifest <private.json>` returns its normalized fingerprint; score files must reference that exact fingerprint. Freeze before tuning, preserve the original manifest separately, and keep whole recordings/setup groups and identical source hashes out of both development and holdout splits.

```powershell
.venv/Scripts/python.exe -m app.inference.cli evaluate --manifest ../config/evaluation-manifest.example.json --scores ../config/evaluation-scores.example.json --split development
```

The evaluator requires a score for every declared case/metric pair. It compares paired scores, resamples independent recording/setup groups, reports a 95% bootstrap interval and refuses to hide a critical per-case regression behind average gains. Minimum group count is configurable before evaluation and is not a power calculation. Scores/provenance flags require audit; the tool never approves release automatically. Development results cannot establish a held-out superiority claim. WER uses explicit whitespace tokenization; select a suitable CER/tokenizer for languages where that is inappropriate. Other metrics are supplied as precomputed audited scores rather than represented as automatically measured footage truth.

`blind --baseline <case-to-text.json> --candidate <case-to-text.json> --seed <integer>` creates randomized A/B forms plus a separate private key. Remove revealing provider labels from source answers before review. Retain reviewer disagreements and adjudication, verify licenses/rules, and assess the full editorial pipeline. Missing baseline outputs, insufficient data or unverified live provenance leave quality inconclusive. No LLM judge can replace source truth and editor assessment.

## Current boundary and checks

`GET /inference/status` reports configuration only and never makes a model call. No public endpoint accepts arbitrary inference payloads. The existing legacy analysis remains separate until integration; enabling this module alone does not migrate the workspace.

Local runtime tests, fixture execution, model discovery and paid/live evaluation were deferred at the owner's request. Syntax, formatting, lint and configuration typing are checked before push. Deferred contract/transport/evaluation tests are included in CI; existing automatic CI/deployment triggers are preserved, and deployment is not polled. A pushed commit is not a successful provider test.

Provider references checked 21 October 2026: [official API](https://api.tokenfactory.nebius.com/docs), [JSON output guidance](https://docs.tokenfactory.nebius.com/ai-models-inference/json), [public endpoint boundary](https://docs.tokenfactory.nebius.com/public-serverless). Support is model-specific; public endpoints do not guarantee a processing region. These references guide adapter structure, not account availability or a validated model selection.
