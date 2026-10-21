# Current capability and implementation evidence

Static inspection on 20 October 2026. “Existing” means located in source, not verified against the live deployment. Phase 1 changes specifications and CI coverage; it does not implement the migration.

| Area | Existing source evidence | Retain / required change | Phase |
| --- | --- | --- | --- |
| Upload/media | [uploads route](../api/app/routes/uploads.py), [storage](../api/app/services/storage.py), [ingest](../api/app/worker/ingest.py) | Retain ingest UX; replace provider-bound upload/storage with controlled staging and root registry | 3 |
| Analysis | [full take](../api/app/services/full_take.py), [agent settings](../agents/trimbin_agents/config.py) | Existing provider integration; implement verified NVIDIA task adapters and new run identity | 4 |
| Evidence/search | [search](../api/app/services/search.py), [ClickHouse migrations](../clickhouse) | Retain useful schema/query semantics; self-host and version index generations | 2, 5 |
| Human corrections | [finding actions](../api/app/services/finding_actions.py), [attempts](../api/app/services/attempts.py) | Preserve corrections/receipts; move operational authority to PostgreSQL | 2, 5 |
| Comparison reuse | [decision run hash](../api/app/services/decisions.py) | Existing key lacks model/prompt versions; replace before new inference is considered fresh | 4, 5 |
| Scene assembly | [stringout](../api/app/services/stringout.py) | Existing selected scene ranges; convert with validated source timing | 6 |
| Film sequence | [film](../api/app/services/film.py) | Existing occurrence IDs, second ranges, revisions and Firestore persistence; retain behavior through precise canonical contract | 6 |
| Handoff | [exports](../api/app/services/exports.py) | Existing scene EDL/marker CSV, zero-based source timecode; new full scene/film FCP7 XML and native manifest | 7 |
| Final video | No complete original-fed film render route identified | Implement immutable-revision render jobs, preflight and fidelity checks | 8 |
| Evaluation | [measurement harness](../eval/run_measurement_eval.py), [misplacement harness](../eval/run_misplacement_eval.py), [fixture generator](../eval/fixtures/build_fixtures.py) | Useful deterministic/specialized checks; insufficient for comparative editorial model quality | 4, 9 |
| Infrastructure | [Terraform environment](../infra/envs/demo), [backend deploy](../.github/workflows/deploy-backend.yml), [web deploy](../.github/workflows/deploy-web.yml) | Terraform resources plus imperative image rollout currently; target full Terraform infrastructure ownership | 2, 9, 10 |
| CI | [CI workflow](../.github/workflows/ci.yml) | Phase 1 adds all-main-push coverage, independent concurrency and documentation checks; deployment triggers retained | 1 |

## Verification and gaps

No frozen paid-output evidence bundle was found in the inspected repository `eval` paths. No cloud export was fetched. Existing synthetic footage generators and a historical code tag are not paid-model answer evidence. The [evaluation protocol](MODEL_CONTRACT.md) specifies how to close this gap.

Current export code rounds timecodes using rounded FPS and does not archive camera start timecode. These legacy limits must not leak into the new precision claims. Existing film history listing is not a complete retention specification. Existing UI playback can use proxy ranges without implying that a high-resolution movie file has been rendered.

Release gates still include real Token Factory access, database/container acceptance, the canonical timeline, actual Premiere import, original-fed video output and portable clean deployment. Implemented code and local fixture checks are distinguished from these gates below.

## Preserve and retire deliberately

Preserve the Apache license, useful existing tests, working runtime and migration references until their replacements pass. Retired documentation/design assets have been moved outside the checkout to `D:\NVIDIA\archive\2026-10-20`; the manifest verifies the 53 original reference files. Legal attribution and truthful reuse history remain intact.

Later phases archive obsolete implementation/configuration only when replacements no longer depend on them. Do not remove functioning source files simply because their provider will eventually change. Keep credentials, original media and private baseline outputs out of this archive and Git.

## Phase 3 implementation evidence

[Media routes](../api/app/routes/media_library.py), [worker](../api/app/media/worker.py), [media page](../web/app/projects/[slug]/media/page.tsx) and [setup](MEDIA_SETUP.md) add mounted sources, resumable uploads, scoped range playback, source hashes, duplicate identity and durable media jobs. Generated footage tests verify selected timing/audio and immutability properties. This path uses PostgreSQL membership and filesystems without Google storage/Firestore/Pub/Sub calls. The legacy analysis and timeline consumers remain unchanged until their phases.

PostgreSQL integration tests and the container manifest are provided, but this PC cannot run Docker/PostgreSQL. HDR proxy processing fails explicitly pending validated tone mapping. Neither broad camera-format support nor comparative AI quality nor a complete migrated editor is claimed.

## Phase 4 implementation evidence

[Inference modules](../api/app/inference) and [operator setup](INFERENCE_SETUP.md) add task contracts, chat/image and embedding adapters, private provenance, model discovery and paired evaluation tooling. Placeholder examples keep live calls disabled. Runtime tests, actual provider access, speech serving and editorial integration remain pending; the implementation is not a measured quality improvement.

## Phase 5 implementation update

The dedicated [evidence workspace](EVIDENCE_SETUP.md) now connects registered deployment sources to original-frame analysis, human annotations/corrections/retractions, slate placement, pinned range selection, selected-text comparison/continuity and scoped text/vector retrieval. PostgreSQL owns revisions and jobs; complete ClickHouse snapshots serve retrieval. API and analysis have explicit provider egress in the portable package. Runtime acceptance remains deferred; this is implemented code, not measured model quality or verified deployment. Legacy editorial routes remain transitional. Canonical timeline assembly and both full exports remain later phases.

## Phase 6 implementation update

The [canonical timeline](TIMELINE_SETUP.md) adds source-frame scene/film editing, linked audio metadata, exact saved conform mapping, revision history and approximate browser preview over the portable media path. Existing revision/receipt storage is reused; no new service or AI credential is needed. Runtime and export acceptance remain pending.
