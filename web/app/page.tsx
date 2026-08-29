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
      router.replace("/dashboard");
    }
  }, [router]);

  return (
    <main className="door">
      <section className="door-inner">
        <h1>Which take, and why.</h1>
        <p className="lede">
          Post-production triage for an editing company. Every take is measured,
          compared against the others of its own shot, and the reason is kept —
          so the question two years from now has an answer.
        </p>

        <div className="door-actions">
          {leaving ? (
            <p className="waiting">Taking you to your work…</p>
          ) : (
            <SignInPanel onSignedIn={() => router.push("/dashboard")} />
          )}
        </div>

        <p className="door-note">
          A guest sign-in gets you a real workspace: your own projects, your own
          footage, the same interface the editors here use. In our productions
          you can read everything, comment on any shot, and overrule any take we
          chose — you just cannot run the panel or upload into them.
        </p>

        <p className="door-links">
          <Link href="/project/1">Look around without signing in</Link>
          <span aria-hidden>·</span>
          <Link href="/about">What this is</Link>
          <span aria-hidden>·</span>
          <Link href="/guide">How to use it</Link>
          <span aria-hidden>·</span>
          <Link href="/accuracy">How often it is right</Link>
        </p>
      </section>
    </main>
  );
}
