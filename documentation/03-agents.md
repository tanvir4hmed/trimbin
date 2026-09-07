# Editorial intelligence

Trimbin separates observation, comparison, retrieval and editorial decisions. Runtime model settings and prompts live in the agents package; application services validate and persist their outputs.

## Identity

The slate reader proposes production codes and evidence. Application policy resolves the proposal or places it in review. An automatic organization choice does not authorize deletion or artistic rejection.

## Independent observation

Full-take analysis covers the recorded duration in 60-second windows with 8-second overlap. It records descriptions, transcript/action context, timecoded moments and findings. Overlap consolidation retains evidence references. A completed run records coverage; it does not prove every possible issue was detected.

Moment spans carry source timing. Their semantic context currently uses the enclosing window's embedding, so fine-grained moment embeddings are a separate enhancement.

The observer also proposes performance attempts inside continuously rolling recordings. Window-edge continuations and repeated action are distinguished; uncertain boundaries remain reviewable. A versioned editorial rubric separates observation, possible creative interpretation, recommendation and confidence. Rack focus, blur, darkness or a subject exit is not automatically an error. These instructions guide the model; they do not establish measured competence or train a new model.

Machine proposals and original structured window outputs are retained independently of human boundary revisions. Adjacent repeated performances are not merged merely because their action descriptions match. Ambiguous cross-window associations require review.

Style-sensitive ingest measurements (such as softness, camera shake, darkness or silence) enter full-duration analysis as descriptive notes, not automatic exclusions. An independently evidenced model or human issue can still require review. Notes are not merged into overlapping faults to enlarge their exclusion ranges. Invalid unlocalized spans are retained in source measurements but not expanded into whole-recording findings.

## Comparative recommendation

Technical, continuity and observable-completion reports inform a chief recommendation. Group-relative measurements help identify outliers but are not a universal guarantee: intentional lighting or camera movement requires context.

The comparative video preview is bounded to 30 seconds; independent full-duration findings provide additional evidence. Do not describe the panel as watching every take uncut. Recommendations and human preferences remain distinct.

## Retrieval

The archivist forms a structured search plan. Application code builds scoped queries and runs retrieval through the official ClickHouse MCP server with a read-only account. Results carry source references and playable ranges. Search does not grant mutation authority, and unavailable retrieval is not represented as an empty archive.

## Human judgement

Editors verify individual findings, select useful portions and record story reasons. The application does not objectively grade acting, infer a performer's true emotions or autonomously direct the film. Export/sequence arithmetic is deterministic; more model calls are not a substitute for valid time ranges and source references.

Review authors can retract their last active finding judgement. Retraction appends an event and restores the preceding state; it does not delete history or withdraw another person's review. Human classification as an intentional technique remains a note rather than an exclusion.

## Research evidence exports

Authorized editors can export per-recording evidence manifests with media hashes, source timing, machine window outputs, attempt proposals/current human boundaries, finding history and current saved film occurrences. Exports contain no media URLs and do not grant training rights. License/participant consent and training eligibility remain unverified; these are review artifacts, not a certified training corpus. Comparison exposure, expert adjudication and full historical sequence exports require additional collection work. Split future evaluations by production/source recording, not overlapping windows.
