"use client";

/**
 * Making a project.
 *
 * Name only. No scene list, no crew, no shoot dates — everything else about a
 * production is discovered from the footage, and a form that asks for it up
 * front is a form somebody abandons.
 *
 * The limits are shown *before* anyone starts. A limit discovered at the moment
 * of failure reads as a bug; the same limit read beforehand reads as a rule, and
 * that difference is most of what separates a guest workspace from a trial.
 */

import { useState } from "react";
import type { Limits, Role } from "@/lib/api";
import { ApiError, api } from "@/lib/api";

export default function NewProject({
  limits,
  role,
  owned,
  onCreated,
}: {
  limits: Limits;
  role: Role;
  owned: number;
  onCreated: (projectId: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isGuest = role === "guest";
  const atLimit = owned >= limits.projects;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const project = await api.createProject(name.trim());
      onCreated(project.project_id);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Could not make that project. Try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        className="primary"
        onClick={() => setOpen(true)}
        disabled={atLimit}
        title={
          atLimit
            ? `You own ${owned} projects, which is the limit for your account.`
            : undefined
        }
      >
        New project
      </button>
    );
  }

  return (
    <div className="new-project" role="dialog" aria-label="New project">
      <label htmlFor="np-name">Project name</label>
      <input
        id="np-name"
        type="text"
        value={name}
        autoFocus
        maxLength={120}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && name.trim()) void submit();
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="Rain scene, day two"
      />

      {isGuest && (
        <p className="np-limits">
          A guest project takes {limits.scenes} scenes, up to{" "}
          {limits.takes_per_shot} takes a shot, and clips up to{" "}
          {limits.clip_seconds} seconds. It is kept for {limits.retention_days}{" "}
          days. You can own {limits.projects}.
        </p>
      )}

      {error && <p className="error small">{error}</p>}

      <div className="np-actions">
        <button
          type="button"
          className="primary"
          disabled={busy || name.trim().length === 0}
          onClick={() => void submit()}
        >
          {busy ? "Making it…" : "Make it"}
        </button>
        <button type="button" className="ghost" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}
