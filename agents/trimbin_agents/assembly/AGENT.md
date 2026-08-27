# Assembly Agent

## Purpose

Apply the panel's verdict, decide in and out points, write the decision log, flag
what needs a person, and produce both the EDL and the streaming manifest.

This is the deliberately boring agent. It sits between AI judgement and what the
editor sees, and almost everything it does is arithmetic rather than inference —
which is the point. A deterministic, auditable step at this boundary is what makes
the whole pipeline trustworthy.

## Contract

| | |
|---|---|
| **Input** | `contracts.assembly.AssemblyRequest` — analysis results for a scene |
| **Output** | `contracts.assembly.AssemblyResult` — selections, flags, EDL, playlist |
| **Writes** | `decisions` (selection rows), EDL and manifest to storage |
| **Model** | Almost none. One short call to phrase the review summary |

## Why almost no model

Ranking, thresholding, sorting and duration maths are SQL. Asking a language model
to compare two numbers is slower, more expensive, and less reliable than comparing
two numbers. The model appears here only to turn a set of findings into a sentence
an editor would want to read.

## MUST NOT

- **Never use an LLM for arithmetic.** If it can be a query, it is a query.
- **Never overwrite a human decision.** An editor's override is appended at higher
  precedence and no later agent run may supersede it.
- **Never delete.** Superseding a scene marks the old material; it does not remove
  it. The entire premise of this product is that nothing is thrown away.
- **Never emit a selection without in and out points.** Editors choose moments
  inside takes, not whole takes. A selection without a span is not usable work.

## In and out points

Default span is the take minus its head and tail — slate, settling, and the beat
after the action ends. Where the Analyst reported timecoded findings, the span is
narrowed to avoid them if a clean run exists, and the reasoning is recorded.

Trimbin does not offer a trimming interface. It marks where the usable material is
and hands that to the editor's NLE, which is better at trimming than anything we
would build.

## Flagging for review

A shot goes to the review queue when any of these hold:

| Condition | Why |
|---|---|
| Margin below threshold | Technically the takes are equivalent, so the decision is emotional — a person's call |
| `winner_id is None` | No take was good enough |
| Any `BLOCKING` finding on the winner | The best available take still has a problem |
| Slate grouping was inferred, not read | The grouping itself may be wrong |

Everything else is decided and needs no attention. The ratio between these two
outcomes is the product's central claim, so it is measured and published.

## The streaming manifest

Selected spans are assembled into a single HLS manifest so the cut plays as one
continuous film with no render step. This works only because every proxy shares
resolution, codec and keyframe placement — a constraint enforced at proxy
generation in Phase 2, not discovered here.

Regenerating the manifest is cheap, so an override is reflected on the next play
rather than requiring an export.

## Failure modes

| Case | Behaviour |
|---|---|
| No clean span exists within the winner | Emit the full take, flag `no_clean_span` |
| Proxy missing for a selected clip | Omit from manifest, flag, keep the EDL entry |
| Manifest generation fails | EDL still written. Export must never depend on playback |

## Cost profile

Negligible. One short call per scene, and only for language.
