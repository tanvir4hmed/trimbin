# Canonical timeline

The sole saved film/scene editor uses frame-based timelines in PostgreSQL with immutable revisions and command receipts. The browser opens `/projects/PROJECT/timeline`; the old film page redirects here. Native/FCP7 export and rendered MP4 pin the same revision.

Sources require verified constant-frame-rate timing and hashes. Human evidence notes/corrections become explicit selections; those selections supply allowed source ranges. A saved occurrence has source ID, selected evidence, in/out frames, note, mute and gain. Clips form a gapless sequence. Unsupported timing/color cases fail visibly rather than guessing a conform.

Existing shot/scene Film controls retain their API shape for compatibility. Their read/save/history routes translate to this same canonical film. A save creates any needed human note/selection and the timeline revision in one PostgreSQL transaction. A bad later range rolls back earlier evidence changes; retries do not create another revision. Reordering preserves existing selections and audio settings. There is no separately writable legacy film document.

Preview uses saved source/range references. Availability checks do not replace export-time source rehashing. Originals remain unchanged. AI drafts are proposals for human approval, not automatic edits. Exact mixed-rate, HDR and external NLE fidelity limits are described in [export contract](EXPORT_CONTRACT.md), [editable export setup](EDITABLE_EXPORT_SETUP.md) and [render setup](RENDER_SETUP.md).
