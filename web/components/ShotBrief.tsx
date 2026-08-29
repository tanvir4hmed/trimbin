"use client";

/**
 * What the shot was meant to be.
 *
 * None of this is invented by us. It is the lined script and the continuity
 * report a script supervisor already writes on every professional shoot — the
 * slug, the action, the line, the note about which hand the cup is in. We are
 * not asking anyone to produce a new artefact; we are the first thing that
 * reads one they already make.
 *
 * All of it optional, and collapsed by default. A production that never fills
 * this in gets exactly what it gets today, because a system that needs
 * paperwork before it is useful is a system nobody opens on a Friday.
 *
 * What it buys, when it is there: the panel stops inferring completeness from
 * majority and starts checking against intent. On a shot where every take
 * drifted the same way, majority is exactly the wrong signal — the whole group
 * can be wrong together, and only the intent says so.
 */

import { useState } from "react";
import type { Brief } from "@/lib/api";
import { api } from "@/lib/api";

export default function ShotBrief({
  projectId,
  scene,
  shot,
  brief,
  canEdit,
  onSaved,
}: {
  projectId: number;
  scene: number;
  shot: number;
  brief: Brief;
  canEdit: boolean;
  onSaved: (brief: Brief) => void;
}) {
  const [open, setOpen] = useState(!brief.is_empty);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [form, setForm] = useState({
    slug: brief.slug,
    heading: brief.heading,
    action: brief.action,
    line: brief.line,
    notes: brief.notes,
    look: brief.look,
  });

  const save = async () => {
    setBusy(true);
    try {
      const saved = await api.saveBrief(projectId, scene, shot, form);
      onSaved(saved);
      setEditing(false);
      setNote(saved.note ?? null);
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Could not save that.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="brief">
      <h3>
        <button
          type="button"
          className="linkish"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          {open ? "−" : "+"} What this shot is meant to be
        </button>
        {brief.is_empty && <span className="hint small">nothing written</span>}
      </h3>

      {open && !editing && (
        <>
          {brief.is_empty ? (
            <p className="hint">
              Optional. With it, the panel checks against intent rather than
              against the majority.
            </p>
          ) : (
            <dl className="brief-fields">
              {brief.slug && (
                <div>
                  <dt>Slate</dt>
                  <dd className="mono">{brief.slug}</dd>
                </div>
              )}
              {brief.heading && (
                <div>
                  <dt>Scene heading</dt>
                  <dd>{brief.heading}</dd>
                </div>
              )}
              {brief.action && (
                <div>
                  <dt>Action</dt>
                  <dd>{brief.action}</dd>
                </div>
              )}
              {brief.line && (
                <div>
                  <dt>Line</dt>
                  <dd>&ldquo;{brief.line}&rdquo;</dd>
                </div>
              )}
              {brief.notes && (
                <div>
                  <dt>Continuity</dt>
                  <dd>{brief.notes}</dd>
                </div>
              )}
              {brief.look && (
                <div>
                  <dt>Intended look</dt>
                  <dd>{brief.look}</dd>
                </div>
              )}
            </dl>
          )}

          {canEdit && (
            <button
              type="button"
              className="ghost small"
              onClick={() => setEditing(true)}
            >
              {brief.is_empty ? "Describe this shot" : "Edit"}
            </button>
          )}
          {note && <p className="hint small">{note}</p>}
        </>
      )}

      {open && editing && (
        <div className="brief-form">
          <label>
            Slate
            <input
              type="text"
              value={form.slug}
              maxLength={40}
              placeholder="12A"
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
            />
          </label>
          <label>
            Scene heading
            <input
              type="text"
              value={form.heading}
              maxLength={200}
              placeholder="INT. APARTMENT - NIGHT"
              onChange={(e) => setForm({ ...form, heading: e.target.value })}
            />
          </label>
          <label className="wide">
            Action
            <textarea
              rows={3}
              value={form.action}
              maxLength={2000}
              placeholder="What happens, from the script."
              onChange={(e) => setForm({ ...form, action: e.target.value })}
            />
          </label>
          <label className="wide">
            Line
            <input
              type="text"
              value={form.line}
              maxLength={500}
              placeholder="You said you would call."
              onChange={(e) => setForm({ ...form, line: e.target.value })}
            />
          </label>
          <label className="wide">
            Continuity notes
            <textarea
              rows={2}
              value={form.notes}
              maxLength={1000}
              placeholder="The cup stays in her left hand."
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </label>
          <label>
            Intended look
            <input
              type="text"
              value={form.look}
              maxLength={60}
              placeholder="handheld, locked off, dolly in"
              onChange={(e) => setForm({ ...form, look: e.target.value })}
            />
          </label>

          <p className="hint small">
            Press <em>Compare again</em> for the panel to use this.
          </p>

          <div className="brief-actions">
            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={() => void save()}
            >
              {busy ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              className="ghost"
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
