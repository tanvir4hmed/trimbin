"use client";

import { FormEvent, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Me, Project } from "@/lib/api";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";

/** A compact project-level team control. Assignment remains per shot. */
export default function ProjectTeam({ project, me }: { project: Project; me: Me }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const people = [project.owner_email, ...project.member_emails].filter(Boolean);
  const mayAdd = project.you_are_owner && project.project_id !== me.demo_project_id;

  const add = async (event: FormEvent) => {
    event.preventDefault();
    if (!email.trim() || busy) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await api.addMember(project.project_id, email.trim());
      setMessage(result.status === "already_a_member" ? "Already on this project." : "Editor added.");
      setEmail("");
      await queryClient.invalidateQueries({ queryKey: keys.project(project.project_id) });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add that editor.");
    } finally {
      setBusy(false);
    }
  };

  return <details className="project-team">
    <summary>Team <span>{people.length}</span></summary>
    <div className="project-team-popover">
      <p className="eyebrow">PROJECT EDITORS</p>
      {people.map((person, index) => <div className="project-person" key={person}>
        <i>{person.slice(0, 1).toUpperCase()}</i>
        <span><b>{person.split("@")[0]}</b><small>{index === 0 ? "Owner" : "Editor"}</small></span>
      </div>)}
      {mayAdd && <form onSubmit={add}>
        <label>Add editor by email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="editor@example.com" /></label>
        <button className="primary" disabled={busy}>{busy ? "Adding…" : "Add editor"}</button>
      </form>}
      {project.project_id === me.demo_project_id && <p className="policy-note">This public example has open review access; its seeded footage stays editor-owned.</p>}
      {message && <p className="policy-note">{message}</p>}
    </div>
  </details>;
}
