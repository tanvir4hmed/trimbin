# Verification and measurement

## Review measurements

GET /quality returns measurements for projects visible to the caller. GET /public/accuracy and /public/accuracy/by-project expose the public-project report. Responses are not cached as static accuracy claims.

**First-review agreement = confirmed unchanged / explicitly reviewed findings.**

Corrections, range adjustments and dismissals belong in the denominator, not the confirmed numerator. Unreviewed findings are excluded. Counts refer to the current completed analysis run and exclude deleted footage and synthetic benchmark projects. A small, self-selected review sample does not establish general model accuracy or recall.

The interface refreshes every 15 seconds and on demand. Completed media processing, placement, analysis and human review update different counters. Durable archive delivery can introduce a short lag.

GET /public/eval is a separate controlled-fault evaluation surface. Synthetic benchmark results must not be described as real-production accuracy.

## Runtime MCP evidence

GET /public/mcp-evidence describes configured search boundaries: official mcp-clickhouse, restricted reader and no direct fallback. Configuration alone is not proof that a particular request executed. Verify a real scoped query and its runtime trace when recording release evidence.

## Engineering checks

From the repository root:

```bash
tools/release-check.sh
```

This runs API/agent tests, formatting/lint, schema freshness, web tests/typecheck/build, Terraform checks and migration numbering. CI adds infrastructure-dependent gates such as migration execution and secret scanning.

Passing these checks does not establish media playback quality, model correctness, accessibility or every workflow. Release evidence should identify its build, data, commands and actually observed results. Do not present incomplete or deferred checks as passed.

## Demonstration workflow

The public example route discovers an available public Anesthesia production by name, without hard-coded authorization. A visitor can inspect its footage, confirmed portions and Film Preview. Signed-in actions are real shared changes, not a resettable sandbox.

A saved film sequence, scene coverage and source footage must remain independent. Show missing selections and unavailable sources explicitly. Demonstration claims must match the deployed revision, not unshipped working-tree features.
