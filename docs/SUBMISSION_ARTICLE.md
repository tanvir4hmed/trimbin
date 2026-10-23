# Submission copy pack — Trimbin

Prepared 23 October 2026 against the implemented code and recorded AWS preflight. The English sections below are ready to paste into the corresponding submission fields. Recheck links, current build, asset rights and remaining access/video fields with [the submission checklist](SUBMISSION_CHECKLIST.md) before submitting. This is drafted material; it is not a claim that a Devpost entry or video has been published.

## Project name

Trimbin

## Tagline

Turn film footage into source-grounded evidence, human-approved edits, editable timelines and original-resolution video.

## Short pitch

Trimbin connects AI-assisted footage review to actual editorial delivery. NVIDIA Nemotron on Nebius Token Factory helps inspect source frames and reason over evidence; editors choose the ranges, and one saved timeline produces editable handoff files or a new video rendered from originals. Portable data services create a foundation for a future studio installation beside SSD/NAS media.

## Inspiration

Movie footage is expensive to move. A film project can contain very large source collections, and a slow or costly connection makes a workflow built around repeated cloud transfers difficult to use. Footage may also be sensitive: a studio needs control over where originals live and which derived inputs leave its network.

Our earlier editorial prototype exposed a second problem. Useful analysis and selected ranges were not a complete delivery workflow. Provider-specific storage and state made the system harder to move, and there was no unified path from human selections to both editable handoff and an original-fed final video.

We expanded Trimbin to address those engineering gaps. The present application runs in the cloud so the complete workflow can be exercised now. The longer-term product direction is a studio software package deployed beside real media storage. We distinguish that future installation from the cloud experiment demonstrated here.

## What it does

An editor opens a project, uploads footage through resumable chunks or registers an operator-authorized mounted source, and lets the system index the original and build separate previews. Original files keep stable identities and content hashes.

NVIDIA Nemotron analyzes timestamped frames decoded from originals and reasons over grounded observations. CPU Whisper provides speech transcription in the editorial analysis path. Editors inspect findings, correct uncertain observations and choose valid source ranges. Text and semantic retrieval help find evidence within the authorized project.

Selected ranges become a saved, frame-based scene or film timeline. Repeated clips are independent occurrences; the editor can order and trim ranges and control supported linked audio. Saved revisions and command receipts protect edits from stale writes and retries.

The same approved revision produces two kinds of output: native/FCP7 editable bundles with original-media relink references, or a new MP4 rendered from the originals. The render does not cut or overwrite the source files. Missing media, invalid ranges and unsupported timing/color cases fail visibly instead of falling back to proxy footage.

## How we built it

Trimbin uses Next.js, FastAPI and separate background worker containers. PostgreSQL owns project authorization, operational documents, evidence lifecycle, immutable timeline revisions, job leases and transactional receipts. Self-hosted ClickHouse stores evidence/history projections and serves scoped text/vector retrieval. FFmpeg and ffprobe handle media inspection, previews and final rendering.

The application uses real runtime calls to Nebius Token Factory. `nvidia/Nemotron-3.5-Super-VL` handles visual input, and `nvidia/nemotron-3-super-120b-a12b` handles reasoning and multi-batch evidence synthesis. `Qwen/Qwen3-Embedding-8B` supplies compatible 768-dimensional retrieval vectors. Speech uses faster-whisper large-v3 on the deployment CPU.

AWS hosts the web application, databases, persistent filesystem and workers. Terraform manages infrastructure, while GitHub Actions uses scoped OIDC, immutable image releases and SSM rollout. Encrypted persistent storage and private S3 backups keep project state separate from replaceable containers. This is one application and one canonical timeline, rather than a new portable layer running alongside a second cloud-dependent editor.

## Challenges we addressed

The real vision endpoint accepts at most eight images per request. Long source windows therefore need bounded batches, validated responses and a reasoning merge. We implemented that path without silently dropping excess supplied frames or treating a failed provider call as successful fixture output.

Timing and identity also mattered. Source frames, sequence frames, audio offsets and repeated occurrences must remain consistent across preview, saved revisions and both exports. We made the timeline authoritative and converted the retained Film API into a facade over that same state. A bad later range rolls back the complete save, and a retried command does not create an extra revision.

Moving off provider-specific document storage and dispatch required replacing runtime dependencies throughout the retained workflow, not just adding new screens. We also exercised real operational problems, including upload promotion across filesystem mounts, writable speech-model caches, embedding dimensions, proxy audio timestamp precision and restored database access roles.

## Accomplishments

We connected real NVIDIA inference, original-media processing, human review, durable selections, canonical editing, semantic retrieval and both output types in a running application.

On the recorded generated-footage AWS preflight, upload/source hashes, real analysis, canonical saves, old Film API retry behavior, semantic search and native/FCP7 export completed. A downloaded 1920 x 1080, 24 fps MP4 had the expected three-second duration and original-frame correspondence. Fresh isolated database containers restored source identities, memberships and timeline state; read permissions and denied DDL were checked after bootstrap.

The Linux API suite passed 602 tests with 18 environment-dependent skips; agents passed 122 and web tests passed 40. These are engineering and integration results, not evidence of superior editorial AI or complete professional NLE compatibility.

## What we learned

A provider replacement is not finished when a new model responds. The complete application must agree on identity, authorization, source timing, durable work and export snapshots. Real endpoint limits and software behavior need runtime checks.

Open models and self-hosted data services can improve deployment flexibility, but they do not remove hosting, inference, storage, backup or electricity costs. Human approval and deterministic media arithmetic remain essential: the model can help organize evidence, while the editor decides and the export engine preserves the chosen ranges.

## Current boundaries and next steps

Our deployment is a single AWS CPU host with external Token Factory inference. Browser uploads and model inputs cross the internet; this is not a zero-upload or offline installation. Terabyte throughput, local GPU performance and customer total-cost savings have not been established.

FCP7 bundle generation and source mapping are tested, but an actual Premiere import/relink acceptance session is still pending. The render supports a declared SDR/cuts/audio subset, not every camera format, effect or HDR workflow. A generated fixture does not establish better movie-quality analysis than the earlier paid model. That claim requires cleared real footage, preserved baseline outputs and independent paired evaluation.

Next we want to close those evaluation and interchange gates, then validate installation beside actual studio SSD/NAS storage and size suitable hardware from measured workloads.

## Significant updates to existing work

Trimbin extends an existing editorial codebase; we do not claim the entire application was created from scratch. We preserved the earlier source boundary and reused useful project, scene/shot/take and review concepts.

During this hackathon edition, we replaced GCP-bound operational storage/dispatch and media dependencies with PostgreSQL and deployment-relative filesystems, self-hosted ClickHouse, integrated real NVIDIA/Nebius inference and CPU speech processing, added durable evidence/corrections and version-compatible retrieval, established one canonical frame timeline, and implemented native/FCP7 export plus original-fed MP4 delivery. We consolidated the old Film API onto that timeline and created Terraform-managed AWS hosting, automatic release configuration and backup/restore checks. The earlier movie corpus was not recovered or fabricated in this deployment.

The key improvement is a working path from source evidence through human-approved edits to actual deliverables, together with a more portable software foundation. It is not just a model or provider rename. Comparative AI quality and future studio hardware benefits remain explicit validation goals.

## NVIDIA and Nebius usage / feedback

Nebius Token Factory provided the real managed inference route for our visual and reasoning tasks. This let us build the cloud experiment without provisioning a GPU model server. Nemotron's role is inside the running application: it analyzes supplied visual evidence and reasons over observations, rather than merely helping write source code.

The integration would benefit from clearer endpoint-specific image limits, explicit embedding-dimension behavior and consistent request-level model/precision provenance. In our tests, the eight-image limit required explicit batching, and retrieval required the requested 768 dimensions to match the index. OpenAI-compatible API structure helped integration, but compatibility alone did not replace runtime contract checks.

AWS hosts unrelated application services. Token Factory credit applies to eligible managed inference, not that AWS infrastructure. Tavily, LangSmith, Toloka and Tendem offers are optional and are not presented as active app integrations or evidence of their API usage.

## Cost / sustainability field

At the checked list rates and a deliberately small hypothetical monthly workload, the whole running application is estimated at about **$167.73/month before tax**, including approximately **$2.56 of model API usage**. Most of the cost is the continuously running CPU host and provisioned disks. This is not a measured price per movie or an unlimited workload plan. Full model token assumptions, every active tool/service, storage growth, credits and exclusions are documented in the cost estimate.

| Basic monthly cost item | Calculation | Estimated USD |
| --- | --- | ---: |
| CPU host | 730 h x $0.19152 | $139.81 |
| Root + persistent data | (40 + 200) GiB x $0.08 | $19.20 |
| Public IPv4 + SSM parameter | 730 h x $0.005 + $0.05 | $3.70 |
| S3 + ECR + small-request allowance | 20 GB x $0.023 + 10 GB x $0.10 + $1 | $2.46 |
| NVIDIA vision | 6M input x $0.30/M + 0.3M output x $0.90/M | $2.07 |
| NVIDIA reasoning | 1M input x $0.30/M + 0.2M output x $0.90/M | $0.48 |
| Qwen embeddings | 1M input x $0.01/M | $0.01 |
| **Total before tax/credits** | Current Free CloudFront plan; shared self-hosted software costs included | **$167.73/month** |

This assumes 300 vision calls and 100 reasoning calls at the stated average billed token sizes, not a fixed number of movie minutes. Whisper, FFmpeg, PostgreSQL and ClickHouse have no separate API invoice here; their host, storage and compute are counted above. Optional partner tools are not used in the basic workload. List-rate sources and all assumptions are in the cost document.


## Built with

Python, TypeScript, FastAPI, Next.js, PostgreSQL, ClickHouse, FFmpeg, faster-whisper, NVIDIA Nemotron, Nebius Token Factory, Qwen embeddings, Docker Compose, Terraform, AWS EC2/EBS/S3/ECR/CloudFront/SSM, GitHub Actions.

## Submission links and track

- Track: Best Apps and Agents.
- Working application: https://trimbin.qleam.com
- Public repository: https://github.com/tanvir4hmed/trimbin
- Setup and documentation: https://github.com/tanvir4hmed/trimbin#readme
- System diagrams: https://github.com/tanvir4hmed/trimbin/blob/main/docs/SYSTEM_DESIGN.md
- Cost assumptions: https://github.com/tanvir4hmed/trimbin/blob/main/docs/COST_ESTIMATE.md
- License: Apache 2.0 for this repository; third-party/model/media licenses remain separate.

The public YouTube URL and private judge-access field must be supplied at submission time. Do not paste owner credentials or API keys into the public description. Do not submit a placeholder URL or call the recording complete before it exists.
