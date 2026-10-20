# Quality strategy

Owner policy recorded 20 October 2026 Asia Dhaka. Status: evaluation specification, not executed results. This policy takes priority over earlier suggestions that a lower-quality model could be accepted for lower cost, simpler implementation or schedule convenience.

## Acceptance target

The goal is better editorial output than the preserved paid-model baseline. Equal output shape or lower API spend is not the improvement claim. No accepted regression in a critical task may be traded against an unrelated gain or hidden by an overall average. Claims of superiority require measured evidence and editor review on a declared scope.

Before evaluation, define critical tasks, labels, primary metrics and what counts as a meaningful improvement for each. Do not introduce a quality-degradation allowance to make a cheap candidate pass. Report sample sizes, uncertainty and observed errors; a small sample with an apparent tie is inconclusive, not proof of superiority. There is no promise that every new answer will beat every old answer.

Treat three questions separately: whether an implementation follows the contract, whether a model produces accurate/useful evidence, and whether the editor gets a better workflow and deliverable. All must be assessed; a passing parser or integration suite does not prove model quality.

## Baseline evidence

Preserve actual outputs from the previous paid-model workflow on cleared source footage. Record source hashes, intervals, model identity/version if available, prompt/configuration, preprocessing, date and relevant editor brief. Configuration strings, the old code tag and historical test counts are insufficient evidence that a live call occurred or that its answer was good.

If prior raw outputs are unavailable, mark the gap. A new paid baseline run needs the owner's applicable credential/budget approval. Reconstructing expected results from fixtures can test contracts, but cannot establish comparative model quality. Use independent editor labels to assess both old and new outputs rather than treating every old answer as truth. Do not use provider outputs as training data without checking the applicable terms and footage rights.

For new export behavior, there may be no prior model-generated deliverable to compare. Use original source frames/audio, the canonical timeline and a controlled NLE reference edit as the correctness reference. Keep this separate from AI-observation comparisons.

## Evaluation corpus

Start with a manageable cleared corpus spanning distinct scenes/productions or shooting setups. Include clean and ambiguous slates, no slate, repeated and late actions, multiple attempts inside one recording, brief gestures, silence, overlapping speech, actual dialogue languages, intentional darkness/blur, handheld footage, similar takes, continuity conflicts and legitimate exceptions.

Reserve whole source recordings/setups for held-out evaluation. Never distribute overlapping windows from the same source between tuning and test sets. Freeze the test set before model/prompt selection. Use multiple independent annotations for difficult comparisons and retain disagreements. Proprietary footage is not sent to external labeling/review services without the required approval and rights.

After choosing a candidate on development data, evaluate the selected full pipeline on the held-out data. If it fails, mark it failed; repeated tuning against that set requires a new uncontaminated test set or an explicit disclosure of reduced evidential strength.

## Task evidence and metrics

| Area | Evidence to collect | Failure to detect |
| --- | --- | --- |
| Slate and grouping | Exact fields, valid abstention, wrong-placement rate and editor corrections | Confidently assigning a clip to the wrong scene/shot |
| Visual observations | Labeled event precision/recall and source attribution | Invented events or missed brief/late events |
| Temporal grounding | Boundary error distribution and cross-window joins | Correct event with unusable timestamps or duplicate/missing joins |
| Dialogue and sound | Transcription errors, speaker attribution and timestamp alignment for actual languages | English-only assumptions, invented words, silence treated as speech |
| Attempts and continuity | Split/merge errors, missed attempts, false continuity claims and paired references | Fabricated mismatch or lost usable performance |
| Retrieval | Relevant source ranges at ranked positions, misses and permission isolation | Fluent answers without the correct material |
| Editorial suggestions | Blind paired editor review under the same brief, reasons and source evidence | Unsupported judgment or generic preference framed as fact |
| Timeline and interchange | Exact source/sequence frames, repeated occurrences, audio layout and actual NLE relinking | Drift, wrong source, missing occurrence or broken conform |
| Render | Source-frame correspondence, selected encoding fidelity, output metadata and audio sync | Proxy-based final output, hidden resampling/color loss or clipping |
| Deployment media workflow | Index/analysis/render completion, peak memory/temp disk and restart recovery on a stated corpus | Scale claim based only on file count or synthetic fixtures |
| Media transfer | Original corpus size, actual inference-input bytes, retries and time on a stated connection | Hiding initial cloud uploads or external inference calls; extrapolating cloud results into tested on-premises operation |

Human review agreement alone is not recall; accepted outputs alone exclude the mistakes never shown to a reviewer. A language-model judge may assist triage but cannot be the sole authority for footage truth or artistic decisions. Blind paired review should conceal provider identity and vary answer order where practical.

## Improving the pipeline before lowering expectations

Use the actual editorial brief, source-grounded context and validated ranges. Preserve temporal resolution for brief events and sufficient image detail for slates, faces and continuity objects. A cheap low-resolution or sparse-frame pass may identify regions for closer inspection, but it is not accepted as the final evidence path until coverage is verified. Escalate uncertain/difficult regions to denser frames, original-resolution crops, appropriate audio input and stronger reasoning where useful.

Long media needs bounded overlapping windows, validated local-to-source offsets, contextual joins and targeted follow-up. Chunking cannot silently omit late actions, window-boundary events or dialogue. Preserve audio channels/timing needed for the task. Avoid using a generated summary as the only evidence when the task needs the actual image, motion or sound.

Compare current suitable open models and task-specific combinations. A larger model, a specialist audio/embedding component or an evidence-checking step may help, but additional agents and repeated calls are not quality proof. Validate the end-to-end combination, including quantization, preprocessing, cache identity and retries, on the same tasks.

Do not reduce FPS, resolution, context, audio coverage, model precision or export bitrate merely to make a hardware/cost target fit. Any such optimization must be evaluated against the approved full-quality reference and pass the same critical-task/fidelity gates. If a machine cannot meet the chosen quality, show the hardware requirement or unavailable state rather than silently degrading.

## Release decision order

1. Establish the user task, source truth, baseline and quality goals.
2. Measure candidates and the complete cloud-hosted editing/export path on a declared corpus.
3. Check the quality-passing choices against competition requirements, licenses, privacy and the actual deployment configuration. Local hardware validation is future work, not a current release gate. Quality and compliance must both pass; neither excuses ignoring the other.
4. Among passing choices, optimize recurring cost, responsiveness, resource use and maintainability.
5. Publish only the measured quality/scale/compatibility scope. Unverified or failed gates remain visible, even near the submission deadline.

If no open-model pipeline meets the quality target, report the missing capability and investigate better data/context, suitable newer models or approved hardware. Do not silently introduce a required closed paid model or claim improvement from cost alone. Any necessary change in scope is an owner decision.

## Evaluation record

Each comparison record identifies dataset/version/split, source intervals, old/new model and prompt revisions, serving precision, sampling and media preprocessing, output-contract validation, task metrics, blind editor judgments, confidence/uncertainty, measured latency/cost, machine details and known limits. Store private media/results in ignored locations; publish sanitized summaries and only redistributable fixtures.

Fixture checks, real API benchmarks, package redeployment checks, NLE import checks and source-render fidelity checks must be reported separately. Actual local GPU/offline tests are deferred; their absence prevents those claims, not completion of the declared cloud edition. No quality experiment has been run by this documentation update.
