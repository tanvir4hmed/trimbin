# Product requirements and competition checks

Status: proposed build requirements. Reviewed 20 October 2026 Asia Dhaka. Implementation status is maintained separately in PHASE_STATUS.md.

## Product purpose

Deliver a complete cloud-hosted editorial application as the proof of concept for a future studio software/hardware package. Large movie footage, limited affordable transfer, provider coupling and incomplete delivery in the prior workflow motivate this expansion. The present edition must demonstrate real analysis, human review, source-range editing and both exports on deployment-hosted media. A local customer installation, offline GPU test, hardware purchase and autoscaling are outside this release.

Use self-hosted portable data services and configurable media roots/endpoints. The cloud experiment proves the tested software workflow and reproducible packaging. A future studio deployment could keep originals on SSD/NAS and use suitable NVIDIA hardware, but zero upload, local performance and lower ownership cost remain unverified future benefits. Browser uploads/staging and external Token Factory inference are disclosed.

The intended audience is editing teams, editor businesses and individual editors handling substantial footage. Retain the valuable existing editorial foundation and show concrete improvements rather than a provider rename. Quality remains non-negotiable against the paid-model baseline; do not accept critical-task regression for cost or convenience. See [product direction](PRODUCT_DIRECTION.md), [quality strategy](QUALITY_STRATEGY.md) and [submission evidence](SUBMISSION_STRATEGY.md).

## Competition baseline

Official rules permit newly created work and significantly updated existing work, with the applicable change explanation. The submission must make a real Nebius execution and use an NVIDIA open model; the chosen Apps and Agents track calls for Nemotron through Token Factory. Deadline: 30 October 2026 at 23:00 Bangladesh time. Individual eligibility, ownership and third-party permissions must be valid. Post-deadline submission changes are restricted. Free judging access must remain available through the judging period. The latest official rules control any conflict. [Rules](https://nebiusglobalaihackathon.devpost.com/rules).

Required package: working demo/test URL, public licensed repository with setup instructions, English materials, selected track, public YouTube demo under three minutes, clear tool/model usage and feedback, plus applicable prior-work explanation. [Overview](https://nebiusglobalaihackathon.devpost.com/).

The whole application need not be hosted on Nebius if its qualifying inference runs there. Promotional Token Factory credits are not a separate AI Cloud GPU/storage grant. An offline-only build or another provider's NVIDIA endpoint alone is insufficient for platform compliance. [FAQ](https://nebiusglobalaihackathon.devpost.com/details/faqs).

Target demo length: 2 minutes 45 seconds. Judging access should cover the published end of judging, 16 December 2026 at 02:00 Bangladesh time, allowing for the Pacific daylight-saving change. Recheck all three official pages at release.

Public docs and UI will describe the current product and current stack. Baseline evidence remains local and in Git. Required prior-work disclosures and license notices must remain truthful even when obsolete marketing names are removed.

## Core user journey

1. Open a hosted project; select cleared preloaded media, upload through the controlled ingest path, or register an allowed deployment-mounted source root.
2. Index originals, derive stable identities and timebases, and create resumable proxy/thumbnail/audio jobs.
3. Analyze bounded windows using a selected real provider, or run an explicitly labeled fixture path for development.
4. Inspect source-linked findings; correct uncertain slate placement, attempt boundaries and issue judgments.
5. Select usable ranges and compare evidence for the desired editorial goal.
6. Assemble selected ranges into scene and film timelines; reorder, trim, preview and save a version.
7. Export an editable timeline with original-media references, or render a new high-resolution output from originals.
8. Reopen the saved project/export evidence and recover cleanly from missing media or an interrupted job.

## Enhancement scope

| Requirement | Required behavior | Acceptance evidence |
| --- | --- | --- |
| Persistent originals | Deployment-hosted originals stay unchanged; references survive restart and root remapping | Source hashes unchanged; relink and missing-media checks |
| Portable cloud package | Reproducible fixed deployment, configurable media roots/endpoints and persistent work | Clean deploy/restart/remap; actual on-premises installation deferred |
| Open model integration | Meaningful Nemotron through Token Factory; contracts allow a future self-hosted endpoint | Real request/result provenance; no hidden provider substitution or claimed local-model certification |
| Quality without concession | Improve on the paid baseline; preserve every critical category; cost and simplicity cannot excuse lower quality | Actual baseline outputs, held-out task metrics, blind editor comparisons and uncertainty |
| Evidence and editorial authority | Findings cite source intervals; uncertain results abstain; users correct and approve | Invalid IDs/times rejected; corrections survive rerun |
| Self-hosted data | ClickHouse for analysis/search; PostgreSQL for operational state and durable jobs | Restart, migration, access scope and recovery checks |
| Selected-range assembly | Scene and film timeline share one canonical representation | Repeated clips, multiple ranges, order and revision tests |
| Editable export | Native timeline plus tested Premiere-compatible interchange | Import and original-media relink in a recorded Premiere version |
| High-resolution render | Originals, not proxies, feed final render | 4K fixture output, cut positions, audio sync and source integrity checks |
| Bounded history | Keep current evidence, human decisions, saved versions and pinned export dependencies | Failed reruns retain complete evidence; saved edits remain resolvable |
| Reliable background work | Analysis/render jobs expose state, progress, retry and cancel | Worker restart/retry and resource-limit fixtures |
| Clear deployment | Main runs checks; preserve approved automatic push deployment; new infrastructure through Terraform | Missing optional keys do not break offline CI |
| Honest demo | Fixture and live inference are clearly differentiated | Demo build and traces identify the actual model and revision |
| Honest transfer claims | Distinguish cloud ingress, private internal traffic and external inference | Stated corpus/input transfers; no zero-upload, offline or certified hardware claim |

## Export boundary

First delivery scope is cuts, source-range ordering, linked source audio, mute/basic gain, chosen sequence frame rate and resolution. Premiere handoff targets Final Cut Pro 7 XML, subject to adapter and actual import testing; it must not be confused with Final Cut Pro X XML. Native timeline JSON and OTIO can retain richer canonical information. [Adobe interchange guidance](https://helpx.adobe.com/ph_fil/premiere-pro/how-to/migrate-from-final-cut-pro.html), [OTIO FCP7 adapter](https://github.com/OpenTimelineIO/otio-fcp-adapter).

Video output starts with MP4 H.264 and AAC at explicit quality settings. A high-quality intermediate is an optional additional preset after codec/platform verification. No arbitrary frame-accurate stream-copy or bit-identical export claim. Source resolution does not imply preservation of every bit-depth, HDR or color attribute; such media must be correctly supported or visibly rejected for the selected preset. Original files remain unchanged. [Export settings reference](https://helpx.adobe.com/ca/premiere/desktop/render-and-export/export-files/overview-of-export-settings.html).

AI draft assembly may propose an arrangement of permitted source ranges with reasons. It requires explicit editor acceptance, creates a new draft, and cannot overwrite saved work. Missing footage or sound cannot be fabricated. Full grading, effects, titles, complex transitions, speed ramps and an attempt to reproduce every NLE feature are outside the initial delivery scope.

## Release gates

- No cross-project access, invalid source references or out-of-bounds ranges accepted.
- No loss of saved selections, referenced attempt versions, sequence revisions or export snapshots.
- Real model evaluation demonstrates the declared improvements over actual paid-model outputs without accepted critical-task regression; a provider benchmark, schema match or low price is not product validation. Missing baseline data keeps the superiority claim unverified.
- The submitted live path makes a genuine qualifying Nebius/NVIDIA call and does not silently replay fixture or old-model output.
- Premiere interchange and rendered video are each tested independently; one passing does not prove the other.
- Local GPU/on-premises validation and autoscaling are deferred, not release gates. Do not publish workstation or terabyte performance claims from this cloud PoC.
- Cleared demo footage, model/codec licenses and application notices are documented. Training and external human review require their own data rights.
- Missing optional partner credits never become a hidden dependency for core editing/export.
- A quality/compliance conflict is reported for an owner decision; neither rule compliance nor claimed cost savings can conceal weaker output.
