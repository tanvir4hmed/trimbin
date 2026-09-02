"use client";

/**
 * Your work: the projects, and how much of each needs a person.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import NewProject from "@/components/NewProject";
import { ApiError } from "@/lib/api";
import { currentIdentity } from "@/lib/auth";
import { useDashboard } from "@/lib/queries";

const THUMBS = [
  "linear-gradient(135deg,#3a3226,#17140f)",
  "linear-gradient(135deg,#2a2f3a,#17140f)",
  "linear-gradient(135deg,#2c3a2e,#17140f)",
  "linear-gradient(135deg,#332a30,#17140f)",
];

/** The verb as a person would say it. */
function say(verb: string, quantity: number): string {
  switch (verb) {
    case "uploaded":
      return `uploaded ${quantity} clip${quantity === 1 ? "" : "s"}`;
    case "compared":
      return `compared ${quantity} take${quantity === 1 ? "" : "s"}`;
    case "chose":
      return `chose take ${quantity}`;
    case "confirmed":
      return `confirmed take ${quantity}`;
    case "undid":
      return "undid a change";
    case "commented":
      return "left a note";
    case "described":
      return "described a shot";
    case "circled":
      return "recorded the circled take";
    case "assigned":
      return "assigned a shot";
    case "set_state":
      return "set the state";
    case "planned":
      return "added to the shot list";
    default:
      return verb;
  }
}

// Undefined as well as null: `at` carries a default in the response model,
// so the generated type makes it optional even though the service always
// sends it. The guard below already covered both; only the signature was
// narrower than the data.
function ago(iso: string | null | undefined): string {
  if (!iso) return "";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days}d ago`;
}

export default function DashboardPage() {
  const router = useRouter();
  const query = useDashboard();
  const data = query.data;

  useEffect(() => {
    if (!currentIdentity()) router.replace("/");
  }, [router]);

  useEffect(() => {
    if (query.error instanceof ApiError && query.error.status === 401) {
      router.replace("/");
    }
  }, [query.error, router]);

  if (query.isPending) {
    return <main className="shell"><p className="waiting">Loading.</p></main>;
  }

  if (query.isError) {
    return (
      <main className="shell">
        <p className="error">
          {query.error instanceof ApiError && query.error.waking
            ? "The archive is waking up."
            : "Could not load your work."}
        </p>
        <button type="button" className="ghost" onClick={() => void query.refetch()}>
          Try again
        </button>
      </main>
    );
  }

  if (!data) return null;

  const waiting = data.totals.waiting;

  return (
    <main className="shell dash home-command">
      <div className="dash-top">
        <div>
          <p className="eyebrow">EDITORIAL WORKSPACE</p><h1>Good morning</h1>
          <p className="dim">Continue where you stopped, or open the next shot that needs a human decision.</p>
        </div>
        <div className="dash-actions">
          {waiting > 0 && (
            <Link href="/review" className="primary">
              Review {waiting}
            </Link>
          )}
          <NewProject
            limits={data.limits}
            role={data.role}
            owned={data.projects.filter((p) => p.you_are_owner).length}
            onCreated={(id) => router.push(`/project/${id}`)}
          />
        </div>
      </div>

      {data.projects.length === 0 ? (
        <div className="first-run">
          <h2>No projects yet</h2>
          <p>Make one and drop a shoot folder into it.</p>
        </div>
      ) : (
        <><div className="home-section-head"><h2>Continue working</h2><Link href="/projects">View all projects →</Link></div><div className="pgrid home-projects">
          {data.projects.slice(0, 3).map((p, i) => (
            <Link key={p.project_id} href={`/project/${p.project_id}`} className="pcard">
              <div className="pthumb" style={{ background: THUMBS[i % THUMBS.length] }}>
                <span className="ptag">
                  {p.you_can_upload ? "yours" : "read & comment"}
                </span>
              </div>
              <div className="pinfo">
                <div className="pname">{p.name}</div>
                <div className="pmeta">
                  Scene · Shot · Take
                  {p.progress_pct !== null && ` · ${p.progress_pct}% settled`}
                </div>
                <div className="pstats">
                  <div className="st">
                    <span className="stn">{p.takes}</span>
                    <span className="stl">clips</span>
                  </div>
                  <div className="st">
                    <span className="stn">{p.shots}</span>
                    <span className="stl">shots</span>
                  </div>
                  <div className="st">
                    <span
                      className="stn"
                      style={{ color: p.waiting ? "var(--amber)" : "var(--faint)" }}
                    >
                      {p.waiting}
                    </span>
                    <span className="stl">need you</span>
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div></>
      )}
      <div className="home-lower"><section><div className="home-section-head"><h2>Needs your decision</h2><Link href="/review">View all {waiting} →</Link></div><div className="home-decisions">{data.queue.length ? data.queue.slice(0,4).map((item) => <Link key={`${item.project_id}-${item.scene}-${item.shot}`} href={`/project/${item.project_id}?scene=${item.scene}&shot=${item.shot}`}><span><b>{item.project_name}</b><small>Scene {item.scene} · {item.slug || `Shot ${item.shot}`}</small></span><span>{item.reason.replaceAll("_", " ")}<small>{item.takes} takes · {item.assignee ? `owner ${item.assignee.split("@")[0]}` : "unassigned"}</small></span><i>Review →</i></Link>)
        : /* An empty column beside a full one read as something failing to
             load. It says which of the two empties it is instead. */
          <div className="home-empty">{data.projects.some((p) => (p.shots ?? 0) > 0)
            ? <><b>Nothing waiting</b><small>Every shot has a chosen take, or somebody is on it.</small></>
            : <><b>No footage yet</b><small>Shots appear here once takes are uploaded and placed.</small></>}
          </div>}</div></section><section><div className="home-section-head"><h2>Recent activity</h2><Link href="/activity">View all activity →</Link></div><ul className="activity home-activity">{data.activity.slice(0,4).map((a,i) => <li key={i}><Link href={a.shot ? `/project/${a.project_id}?scene=${a.scene}&shot=${a.shot}` : `/project/${a.project_id}`}><span className="who">{a.actor.split("@")[0]}</span> <span className="what">{say(a.verb,a.quantity)}</span><span className="where">{a.project_name}</span></Link><span className="ago">{ago(a.at)}</span></li>)}</ul></section></div>
    </main>
  );
}
