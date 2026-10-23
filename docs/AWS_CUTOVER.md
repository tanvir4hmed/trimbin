# AWS cutover and verification

Updated 23 October 2026. The owner authorized the full non-demo cutover on main, paid AWS hosting, supplied Token Factory credentials, and pre-push runtime verification. The application is running at https://trimbin.qleam.com. This report describes the preflight build tested before the final main push; it does not certify the later GitHub Actions run.

## One application and one authority

| Area | Current implementation |
| --- | --- |
| Application | `app.main`, the existing editorial UI and new media/evidence/timeline screens; one production Compose definition |
| Projects, membership and editorial documents | PostgreSQL; retained document-style calls are backed by transactional PostgreSQL, not Firestore |
| Jobs and events | PostgreSQL leases, receipts and outbox; editorial ingest and analysis no longer publish to Pub/Sub |
| Source media and derivatives | Encrypted persistent EBS filesystem; authenticated chunk uploads, mounted library, range playback and immutable source identities |
| Evidence and retrieval | Self-hosted ClickHouse with separate writer and read-only identities; projection and semantic-vector workers |
| Film state | One canonical frame timeline. The old Film API is a compatibility facade over it, with shared revisions and idempotent saves |
| AI | Real Token Factory NVIDIA vision/reasoning, Qwen embeddings and local CPU Whisper; no Vertex/Gemini application runtime |
| Final delivery | Native timeline ZIP, FCP7 XML ZIP and original-fed MP4 for the documented SDR subset |
| Infrastructure | Terraform AWS resources; GitHub main-push checks, immutable ECR images, private release archive and SSM rollout |

Old GCP Terraform, deployment workflows and replaced container packages were hash-preserved outside Git at `D:/NVIDIA/archive/2026-10-23-aws-cutover`. Nine obsolete GCP/managed ClickHouse GitHub secrets were removed. The protected `agentic-cinema-final-submission` tag and truthful reuse/license provenance remain intact. There is no parallel GCP-backed production workflow. The foundation Compose package is a disposable database development/CI fixture.

## Provisioned deployment

Account 552794253321, region us-east-1. Terraform owns the trimbin VPC/network/security group, SSM-managed m7i-flex.xlarge CPU host (4 vCPU, 16 GiB), encrypted 40 GiB root and 200 GiB persistent data disks, EIP, ECR repositories, private versioned state/release/backup buckets, runtime parameter and scoped instance/GitHub roles. No GPU, Kubernetes or autoscaling was provisioned. Unrelated AWS instances were not modified.

The existing CloudFront distribution E147Q68AK9MRYP, domain alias, issued certificate and WAF were retained/imported. Its previous redirect/origin behavior was replaced with the Trimbin origin. Viewer traffic uses HTTPS; CloudFront-to-origin currently uses HTTP restricted to AWS CloudFront origin addresses. Database ports and SSH are not public. This is a single-host PoC, not high availability or end-to-end encrypted private networking.

GitHub uses OIDC scoped to `tanvir4hmed/trimbin` main. Actual repository Variables identify the role, instance, ECR registry, release bucket and distribution. Runtime credentials are encrypted in SSM `/trimbin/runtime`; generated operator files are ignored under `.secrets/aws`. No secret values are in this report. AWS hosting/storage/transfer and future inference usage remain chargeable separately from promotional credits.

## Real model execution

- Vision: `nvidia/Nemotron-3.5-Super-VL`.
- Reasoning: `nvidia/nemotron-3-super-120b-a12b`.
- Embeddings: `Qwen/Qwen3-Embedding-8B`, explicitly requested 768 dimensions with L2 normalization.
- Speech: `Systran/faster-whisper-large-v3`, CPU int8, persistent model cache.

The real vision endpoint rejects more than eight images per request. The adapter batches larger supplied frame sets, validates every batch and merges observations using NVIDIA reasoning; it does not silently discard excess images. Twelve-image execution (8 + 4) and the reasoning merge were exercised on generated footage. Frames come from originals, with source/window labels and bounded sampling. This is sampled visual analysis, not proof of detecting every transient event. Managed aliases do not pin weight revisions or disclose provider precision. No successful fixture call was substituted for a provider result.

## Runtime evidence

The private `Trimbin verification` workspace uses explicitly generated six-second 1920 x 1080 footage, including a tagged Rec.709 source. It is distinct from the owner's empty workspace and from unrecovered historical movie data.

| Check | Observed result |
| --- | --- |
| Public endpoint and authentication | HTTPS app/projects and API readiness returned 200; password login and secure HttpOnly cookie verified |
| Shared project identity | Editorial and workflow APIs address the same PostgreSQL projects |
| Upload and derivatives | 8 MiB resumable chunks, matching source SHA256, original/proxy/sprite/audio jobs completed |
| Real analysis | NVIDIA original-frame evidence and complete full-take analysis published; CPU Whisper completed and abstained from speech on synthetic tone |
| Human authority | Notes, selected ranges and canonical scene/film revision saves exercised |
| Film compatibility | Old Film API save/replay updated the same canonical film to revision 4, without writing a second film document |
| Retrieval | Automatic evidence/vector projection followed by a real Qwen semantic query returned 11 scoped results |
| Editable handoff | Native and FCP7 ZIP jobs completed; downloaded manifest checksums verified; XML sequence frames 0..72 mapped to source frames 24..96 |
| Original-fed render | Downloaded 1920 x 1080, 24 fps, 3.000-second MP4; Rec.709 tags and output SHA256 checked; first frame matched source frame 24 (PSNR 52.264 dB on this fixture) |
| Persistence/release | Repeated preflight image deployments retained projects, source identities and saved edits |
| Backup/restore | Quiesced production backup plus isolated database restore; details below |

The fixture fidelity result is not a claim of lossless export, Premiere equivalence, general movie quality, 4K throughput or superior AI accuracy. The render supports the documented cuts/audio/SDR subset and rejects unsupported cases.

## Recovery rehearsal and operator procedure

The production backup script completed at `20261023T130124Z`: writers stopped together, PostgreSQL custom dump and ClickHouse native database backup were taken, originals/exports copied to the private S3 backup bucket, and workers restarted. Daily systemd scheduling is installed by the release script. The backup is downtime-based, without online point-in-time recovery.

An isolated PostgreSQL database restored 3 media sources and 2 projects. An isolated ClickHouse database restored the schema/migration ledger, 3 clips, 26 analysis-run records, 7 clip moments and 8 evidence snapshots. A second rehearsal restored into fresh pinned database containers on a separate internal network. Production bootstrap passed with the restored ledger and recreated ClickHouse roles/profiles/grants; reader and writer SELECT succeeded while DDL was denied. Restored source fingerprints, memberships and canonical timeline bodies/revisions matched production. Database backups do not automatically restore those access entities. Credentials and machine configuration must be recovered separately from SSM or protected operator storage.

For an incident, stop writers and preserve the existing disks first. Provision a separate recovery host/storage using Terraform, initialize roles using the pinned images and protected configuration, restore the matching PostgreSQL dump and ClickHouse native backup, restore originals/exports from the private bucket, and run production bootstrap. Verify source hashes, project memberships, saved timeline revisions, export manifests and read/write permission boundaries before reopening writers or switching the domain. Do not restore over the only original disk or treat an image rollback as a database rollback. Root remapping and an actual replacement-host disaster recovery exercise remain separate from the isolated database rehearsal.

## Checks and remaining release gates

Linux API tests: 602 passed, 18 environment-dependent skips; the live isolated PostgreSQL tests are covered by that run. Agents: 122 passed; mypy checked 27 source files. Web tests, TypeScript and production build passed. OpenAPI-generated TypeScript matched the API. Lint/format, documentation targets, actionlint, Terraform validation and redacted secret scanning are checked before commit. Private logs and generated artifacts remain outside Git.

Not established: paired improvement over the former paid-model outputs, actual Premiere import/relink acceptance, a cleared real-movie evaluation corpus, restored historical GCP media/state, terabyte performance, offline/self-hosted GPU execution, customer hardware performance, broad HDR/camera-format support or high availability. These gaps remain visible; deployment success does not waive the quality policy. Demo recording, judge credentials, public submission material and video are the separate next phase.

The final push triggers the new deployment workflow. Per owner instruction its resulting run is not polled after pushing; that workflow performs its own health checks and reports failures.
