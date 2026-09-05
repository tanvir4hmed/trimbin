"use client";

/**
 * The door.
 *
 * This page used to be nine screens of prose: the problem, the method, Murch,
 * an honest list of what is not built. All of it worth reading and none of it
 * what somebody arriving at an application is looking for. A person landing
 * here does not read; they look for the way in.
 *
 * So: one screen, two buttons, and everything that was here moved to /about
 * where it can be read by anyone who wants it. A signed-in person is sent
 * straight to their work — the front door of a tool you use every day should
 * be the tool.
 *
 * The door is rendered unconditionally, not held back until the session check
 * finishes. Holding it back is the obvious way to avoid showing it to somebody
 * who is already signed in, and it costs far more than it saves: effects run
 * after paint, so the page ships as an empty element and anything without
 * JavaScript — a crawler, a preview card, a slow connection mid-load — gets a
 * blank page. A signed-in person sees this for the length of one frame instead.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import SignInPanel from "@/components/SignInPanel";
import { currentIdentity } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    if (currentIdentity()) {
      setLeaving(true);
      router.replace("/home");
    }
  }, [router]);

  return (
    <main className="door">
      <section className="door-inner">
        <p className="door-kicker">EDITORIAL OPERATIONS · TAKE INTELLIGENCE</p>
        <h1>Review the day. Keep the decision.</h1>
        <p className="lede">
          Trimbin organizes footage by scene and shot, shows every take’s usable
          ranges and technical issues, and keeps human choices searchable.
        </p>

        <div className="door-actions">
          {leaving ? (
            <p className="waiting">Taking you to your work…</p>
          ) : (
            <SignInPanel onSignedIn={() => router.push("/home")} />
          )}
        </div>

        <div className="door-workflow" aria-label="What Trimbin does"><span><b>01</b> Verify ingest</span><span><b>02</b> Review every take</span><span><b>03</b> Play scene coverage</span></div>

        <p className="door-links">
          <Link href="/about">About</Link>
          <span aria-hidden>·</span>
          <Link href="/guide">Guide</Link>
          <span aria-hidden>·</span>
          <Link href="/accuracy">Accuracy</Link>
        </p>
      </section>
    </main>
  );
}
