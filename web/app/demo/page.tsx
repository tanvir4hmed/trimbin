"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { paths } from "@/lib/slug";
import { currentIdentity } from "@/lib/auth";

export default function ExampleProjectPage() {
  const query = useQuery({
    queryKey: [
      "projects",
      true,
      "example",
      currentIdentity()?.email ?? "anonymous",
    ],
    queryFn: () => api.projects(true),
  });
  const publicProjects = (query.data?.projects ?? []).filter(
    (p) => p.is_public,
  );
  const project =
    publicProjects.find((p) => /anesthe?sia/i.test(p.name)) ??
    publicProjects[0];
  return (
    <main className="shell prose">
      <section>
        <p className="eyebrow">EXAMPLE PRODUCTION</p>
        <h1>Start with the output. Follow the evidence.</h1>
        <p className="lede">
          Explore a real shared production: its source takes, reviewed issues,
          confirmed portions and Film Preview. This is a working project, not a
          resettable sandbox.
        </p>
      </section>
      {query.isPending ? (
        <p className="waiting">Loading the example project…</p>
      ) : query.isError ? (
        <p className="error">
          The project list could not load.{" "}
          <button className="ghost" onClick={() => void query.refetch()}>
            Retry
          </button>
        </p>
      ) : project ? (
        <section className="example-production">
          <h2>{project.name}</h2>
          <p>
            {project.scenes ?? 0} scenes · {project.shots ?? 0} shots ·{" "}
            {project.takes ?? 0} clips
          </p>
          <div className="example-actions">
            <Link
              className="primary"
              href={paths.film(project.project_id, project.name)}
            >
              Film Preview
            </Link>
            <Link
              className="ghost"
              href={paths.project(project.project_id, project.name)}
            >
              Explore scenes &amp; takes
            </Link>
            <Link
              className="ghost"
              href={`/accuracy?project=${project.project_id}`}
            >
              View review measurements
            </Link>
          </div>
        </section>
      ) : (
        <p>
          No public example is currently available.{" "}
          <Link href="/projects">Browse projects</Link>.
        </p>
      )}
      <section>
        <h2>Three things to explore</h2>
        <ol>
          <li>
            Watch current confirmed portions across the production, or its saved
            sequence.
          </li>
          <li>
            Open a shot and trace a decision back to a take, a range and its
            evidence.
          </li>
          <li>
            Sign in to review, select portions, comment or upload your own
            footage within your access.
          </li>
        </ol>
        <p>
          Changes are real and shared. Do not remove someone else's material.
          Observations are suggestions for an editor to verify—not a guarantee
          that a take is fault-free.
        </p>
        <Link href="/guide">Read the short workflow guide →</Link>
      </section>
    </main>
  );
}
