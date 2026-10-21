# Model tasks and quality evaluation protocol

Phase 1 specification. No provider call, model-quality benchmark or account model discovery was performed in this phase. Follow [quality strategy](QUALITY_STRATEGY.md); cost does not justify a critical-task regression.

## Task boundaries

| Task | Required input | Valid output and abstention |
| --- | --- | --- |
| Slate/grouping | Readable source frames/crops, permitted project labels | Extracted fields and source evidence; uncertain/no-slate instead of invented grouping |
| Visual observations | Timestamped frames or supported video with sufficient temporal coverage | Events/objects/actions with bounded source intervals and uncertainty |
| Speech/audio | Supported source audio preserving timing/channels and actual language | Words/speakers/times, uncertainty or no speech; never derive a transcript from silent images |
| Attempts/continuity | Ordered evidence, relevant image/audio context, paired source ranges | Attempt boundaries and cited mismatches; distinguish artistic preference from observable facts |
| Comparison/reasoning | Editorial brief, permitted candidates and source-linked evidence | Ranked candidates, reasons and uncertainty; no unavailable candidate |
| Retrieval | Project-authorized corpus and query with compatible embedding generation | Ranked source ranges and citations; empty result distinct from unavailable index |
| Draft assembly | Explicit allowed ranges, brief and timeline constraints | Ordered proposed occurrences with reasons; no save/overwrite until editor accepts |

Nemotron through Token Factory must perform a meaningful supported task in the submitted route. A model name in a config file is insufficient. At Phase 4, discover account-accessible exact IDs, supported request modalities, limits, licenses and pricing. Record a real validated request before treating an adapter as live. Do not assume a reasoning endpoint supports video/audio or that similarly named models share an API.

Select task-specific open models on evidence, not a version label alone. No mandatory closed-model dependency is planned. Optional LangSmith, Tavily, Toloka and Tendem are not substitutes for missing footage truth or live model quality.

## Request, response and cache envelope

Requests identify project, task/schema version, source versions/intervals, preprocessing recipe, timestamp origin, evidence revision, editorial brief revision and allowed output IDs. The server constructs permitted media inputs and validates source scope before transmission. Record byte counts and disclose outbound inference inputs.

Responses retain provider request ID where available, exact model/revision, inference settings, prompt hash/version, input fingerprint, output schema version, validation result, latency, usage and error category. Persist the original response privately when rights permit, plus normalized evidence. Unknown usage/cost remains unknown, not zero.

Validate every ID, interval and citation against the request. Invalid or partially parsed output is a failed attempt, not complete evidence. Bounded schema-repair attempts are new recorded attempts. Unsupported modality, authentication, quota, timeout and provider rejection produce distinct recoverable states. Do not silently substitute old cached output or a cheaper model.

Cache identity includes project scope, source content versions, task, provider/model revision, serving precision where known, prompt/schema/adapter versions, sampling/audio recipe, inference parameters, relevant evidence and brief revisions. A full analysis generation publishes only when all required windows/tasks pass. Optional missing tasks remain explicitly unavailable.

Embeddings identify model, dimension, normalization, preprocessing and index generation. Corpus and query must match that identity; equal dimensions do not establish compatibility. A changed model builds a new index and switches readers only after validation.

## Baseline availability and corpus freeze

The protected Git tag proves a code boundary only. Current repository evaluation scripts provide synthetic measurement tests and an embedding misplacement harness; they are not a frozen paid-model comparison dataset. No eligible historical output bundle was found in the inspected repository evaluation paths. Private cloud/account data was not queried; availability there is unknown.

Before Phase 4 comparisons, obtain cleared recordings and actual historical outputs with model/prompt/preprocessing provenance. If unavailable, record the gap and seek an explicitly budgeted baseline run; do not manufacture a baseline. Contract fixtures may proceed independently.

Freeze a manifest of source hashes, rights, whole-recording/set-group splits, labels, annotators, critical categories and metrics before candidate evaluation. Keep overlapping windows and related takes/setups out of different splits. Reserve a held-out test split untouched by prompt/model tuning. A small corpus is exploratory; sample size must support the intended claim, and weak uncertainty keeps the outcome inconclusive.

## Predeclared evaluation decisions

| Task | Primary measurements | Passing principle |
| --- | --- | --- |
| Slate/grouping | Exact fields, false placement, abstention coverage | No critical increase in wrong placements; compare abstention honestly |
| Events and continuity | Precision/recall, false mismatch rate, missed brief/late actions | No critical category regresses; report counts per category |
| Temporal grounding/attempts | Boundary error distribution, split/merge errors, window joins | Editor-defined tolerances frozen before evaluation |
| Dialogue | WER/CER as suitable, speaker and timestamp accuracy by language | No hiding a language failure in aggregate |
| Retrieval | Recall@k, nDCG@k, missed relevant intervals | Same query set/corpus; project leakage is an automatic failure |
| Editorial preference | Blind paired editor assessment and justified ties | Better supported creative utility, not merely more fluent reasons |
| Contract correctness | Invalid IDs/ranges/schema and fabricated sources | Zero accepted invalid outputs |

For quality metrics, use paired comparisons on the same independent recordings, report sample sizes and uncertainty (resample at recording/setup level, not overlapping-window level). Zero observed regression on a tiny set is not established non-regression. The critical-task policy has no allowed degradation margin; lack of power is inconclusive. Establish a meaningful improvement threshold with labeled development examples before looking at held-out results.

Model selection occurs on development data. Evaluate the chosen full pipeline on held-out data once; tuning after failure contaminates that set and needs a fresh holdout or explicit limitation. Blind reviewers see randomized A/B order without provider labels. Disagreements are retained and adjudicated; an LLM judge cannot be the sole truth source.

Release requires supported improvement on declared primary goals, no accepted critical regression, real platform execution and rights/license compliance. If the evidence is insufficient, publish no superiority claim and keep the gate open. Lower latency/token spend is a separate optimization among quality-passing configurations.

## Evidence record

Each result bundle contains dataset/split hashes, baseline/candidate identities, code build, machine and preprocessing, task outputs, per-case scores, aggregate uncertainty, blind review, failures, retries and measured time/cost. Private media/raw responses stay outside Git. Publish sanitized summaries only. Contract fixtures, live provider tests, NLE compatibility and export fidelity have separate status fields.

## Phase 4 implementation boundary

[Adapter setup](INFERENCE_SETUP.md) documents the implemented request/result validation, Token Factory transport, embedding identities, private run records and evaluation CLI. Runtime and quality testing were deferred by the owner. No account-accessible model ID or superior pipeline has been verified; actual baseline data and cleared gold annotations remain missing inputs. The current adapter accepts text evidence and explicit original-detail image assets; automatic window/frame preparation and editorial persistence are next-phase integration. Unsupported speech is a visible unavailable state, not a fabricated transcript.
