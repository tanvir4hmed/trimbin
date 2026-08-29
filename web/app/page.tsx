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
 * where it can be read by anyone who wants it. A signed-in person never sees
 * this page at all — they are already working, and the front door of a tool you
 * use every day should be the tool.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CLIENT_ID, currentIdentity, renderSignInButton } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (currentIdentity()) {
      router.replace("/dashboard");
      return;
    }
    setChecked(true);
  }, [router]);

  useEffect(() => {
    if (!checked || !buttonRef.current) return;
    void renderSignInButton(buttonRef.current, () => router.push("/dashboard"));
  }, [checked, router]);

  if (!checked) {
    // Nothing rather than a flash of the door for somebody who is already
    // inside. The redirect lands within a frame; a marketing page appearing
    // first would read as being signed out.
    return <main className="door" />;
  }

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
          {CLIENT_ID ? (
            <div className="signin big" ref={buttonRef} />
          ) : (
            <p className="hint">
              Sign-in is not configured on this deployment. See
              docs/oauth-client.md.
            </p>
          )}
          <Link href="/project/1" className="ghost">
            Look around a real project
          </Link>
        </div>

        <p className="door-note">
          Sign in with any Google account and you get a real workspace: your own
          projects, your own footage, the same interface the editors here use.
          In our productions you can read everything, comment, and overrule any
          call we made.
        </p>

        <p className="door-links">
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
