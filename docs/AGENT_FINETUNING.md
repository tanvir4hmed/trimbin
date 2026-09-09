# Agent finetuning — 2026-09-09

Scope: backend/agent changes only. No frontend, navigation, CSS, response-schema,
database migration or deployment-workflow changes. Baseline: `b7098c4`.

## Audit and implementation

- Agent/backend code at baseline matched `v4.0`. The segment observer in `v3.0`
  was `segment/v2`; `v4.0` used `segment/v3`. The new behavior has its own
  `segment/v4` prompt, retaining bounded-window attempts and human editorial authority.
- Strengthened evidence rules for slate/clap/action/cut, motion, focus, obstruction,
  continuity references, completion and uncertain cinematic intent. A prompt change
  is not model training or proof of improved real-footage accuracy.
- Existing authenticated `POST /analysis/{project_id}/backfill` now includes completed
  runs from obsolete prompt versions. Existing active-run leases, unique generations,
  completed-run publication, model/context run keys and retry fencing are retained.
  No production backfill was executed during this work. Re-analysis uses paid model
  calls when requested; deployment alone does not replay the archive.
- Human accept/dismiss/adjust history remains separate and attributed. Old-run human
  decisions remain in history, not silently transferred onto new-run finding IDs.
  Existing saved editorial selections are not rewritten by model re-analysis.
- Every explicitly confirmed/corrected/range-adjusted issue now excludes its exact
  interval from backend safe suggestions, even if short or normally only a note.
  Shot comparison retains the human action field. Dismissal restores candidate time.
- Coverage saves validate all source ranges against each other and current issue
  evidence, including pending human actions in Firestore. Conflicts return 422 before
  commit; no silent draft rewrite. Existing browser crop-and-save behavior is unchanged.
  Intervals are half-open: adjacent frame boundaries need no artificial one-second gap.
- Motion spikes already ran in v4.0. Fixed the zero-baseline blind spot while retaining
  sustained-event and black/freeze exclusion gates. Added localized ffmpeg silence
  measurements, preserving audible gaps and finite loudness values for digital silence.
  Silence is not classified as a microphone failure or proven dropout.
- EDL source and record durations now use the same integer-frame accounting, avoiding
  cumulative subframe drift. Output names zero-based camera-TC limitations and missing
  filenames/proxy metadata. Marker export intersects used source intervals, supports
  multiple portions of a take, and no longer pins excluded defects onto clean frames.
- Existing common editorial rubric, Murch priorities, nullable winner, searchable
  moments/transcript and MCP-only runtime search were retained, with existing tests.

## Resolve Guide comparison and boundaries

Reference: `D:/DEVPOST/DaVinci-Resolve-20-Editors-Guide.pdf`, printed pages
150 (separate takes), 178 (take selector/creative compromise), 278 (metadata),
324 (proxies), 341 (transcription), 548 (AAF), 608 (export verification).

Trimbin supports assistant-editor evidence, source-range choices, proxies, human
review and handoff, not all Resolve functions. Ripple/roll/slip/slide editing,
multicam, grading, Fusion, full audio mixing and render presets remain outside scope.
AAF/XML are deferred: no verified NLE round-trip or original camera timecode/reel
metadata exists to justify claiming a reliable conform. EDL remains non-drop and
zero-based; CSV/native-NLE import still needs testing in the target application.

## Verification and follow-up

- API: 506 passed, 18 skipped (no local `CLICKHOUSE_URL`; parser tests require it).
- Agents: 120 passed; mypy passed; API and agents ruff checks/format passed.
- Frontend: 28 passed, TypeScript check passed, production Next build passed.
- Added executable synthetic PCM silence/tone fixtures, motion/flash tests, exact
  issue subtraction, endpoint save rejection, prompt backfill selection, human-action
  propagation, multi-range markers and frame-accounting regressions.
- No labelled production-footage model evaluation or live Vertex/MCP smoke run was
  performed. Real precision/recall cannot be inferred from deterministic tests.
- New deterministic silence measurements apply on ingest, not retroactively when
  only semantic model backfill is requested. Existing archive evidence is preserved.
- Source/frame-rate relink verification in Resolve/Premiere and a human-labelled
  representative footage evaluation set remain required follow-up work.

Deploy through the requested single `agent finetuning` commit pushed to `main`.
Existing path filters select backend deployment; frontend deployment is not triggered
by these paths. The backend workflow still runs the shared CI suite, including web checks.
