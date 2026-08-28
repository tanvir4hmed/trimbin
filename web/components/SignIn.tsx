"use client";

/**
 * The sign-in control in the header, and the project switcher beside it.
 *
 * Both are deliberately quiet. Every page a visitor is likely to land on works
 * without an account, so this is not a gate — it is a control that appears once
 * you have a reason to use it.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CLIENT_ID,
  Identity,
  currentIdentity,
  currentToken,
  renderSignInButton,
  signOut,
} from "@/lib/auth";

interface Project {
  project_id: number;
  name: string;
  you_are_owner: boolean;
}

const API = process.env.NEXT_PUBLIC_API_BASE ?? "/api";
const SELECTED_KEY = "trimbin.project";

export default function SignIn() {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const buttonRef = useRef<HTMLDivElement>(null);

  // Read the stored session on mount rather than during render. sessionStorage
  // does not exist while Next renders on the server, and reaching for it there
  // makes the first paint disagree with the second.
  useEffect(() => {
    setIdentity(currentIdentity());
  }, []);

  const loadProjects = useCallback(async () => {
    const token = currentToken();
    if (!token) return;

    try {
      const response = await fetch(`${API}/projects`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.status === 401) {
        // The token expired between mounting and asking. Signing out is
        // honest; retrying with the same token would loop.
        signOut();
        setIdentity(null);
        return;
      }
      if (!response.ok) throw new Error(`${response.status}`);

      const body = await response.json();
      const found: Project[] = body.projects ?? [];
      setProjects(found);

      const remembered = Number(localStorage.getItem(SELECTED_KEY));
      const valid = found.some((p) => p.project_id === remembered);
      setSelected(valid ? remembered : (found[0]?.project_id ?? null));
    } catch {
      setError("Could not load your projects.");
    }
  }, []);

  useEffect(() => {
    if (identity) void loadProjects();
  }, [identity, loadProjects]);

  useEffect(() => {
    if (identity || !buttonRef.current) return;
    void renderSignInButton(buttonRef.current, (who) => {
      setIdentity(who);
      setError(null);
    });
  }, [identity]);

  const choose = (id: number) => {
    setSelected(id);
    try {
      localStorage.setItem(SELECTED_KEY, String(id));
    } catch {
      // A remembered choice is a convenience, not state the app depends on.
    }
    window.dispatchEvent(new CustomEvent("trimbin:project", { detail: id }));
  };

  if (!CLIENT_ID) {
    // Nothing at all rather than a button that cannot work. See
    // docs/oauth-client.md.
    return null;
  }

  if (!identity) {
    return <div className="signin" ref={buttonRef} />;
  }

  return (
    <div className="signin signed-in">
      {projects && projects.length > 0 && (
        <select
          className="project-switcher"
          value={selected ?? ""}
          onChange={(e) => choose(Number(e.target.value))}
          aria-label="Project"
        >
          {projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.name}
              {p.you_are_owner ? " ·" : ""}
            </option>
          ))}
        </select>
      )}

      {projects?.length === 0 && (
        <span className="hint">No projects yet</span>
      )}

      {error && <span className="hint error">{error}</span>}

      <button
        type="button"
        className="signout"
        onClick={() => {
          signOut();
          setIdentity(null);
          setProjects(null);
        }}
        title={identity.email}
      >
        {identity.name.split(" ")[0]} · sign out
      </button>
    </div>
  );
}
