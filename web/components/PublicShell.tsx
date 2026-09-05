"use client";

/**
 * The frame for the pages a stranger lands on.
 *
 * About, Guide, Accuracy and Demo are evidence, not daily work: a judge reads
 * them once, and they should not carry the editing sidebar. But retiring the
 * old top bar left them carrying *nothing* — no wordmark, no way back, no way
 * in. A page publishing this system's own error rate with no route to the
 * product is a dead end wearing a dark background.
 *
 * So: a thin bar, the same palette as the application, and a way in. It is
 * deliberately not the app sidebar — these pages are not places you work.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { currentIdentity, type Identity } from "@/lib/auth";

const LINKS = [
  ["/about", "About"],
  ["/guide", "How it works"],
  ["/accuracy", "Accuracy"],
  ["/demo", "What is built"],
] as const;

export default function PublicShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [identity, setIdentity] = useState<Identity | null>(null);

  // Read after mount: sessionStorage does not exist while Next renders on the
  // server, and reaching for it there makes the first paint disagree with the
  // second.
  useEffect(() => {
    setIdentity(currentIdentity());
    const refresh = () => setIdentity(currentIdentity());
    addEventListener("trimbin:auth", refresh);
    addEventListener("storage", refresh);
    return () => {
      removeEventListener("trimbin:auth", refresh);
      removeEventListener("storage", refresh);
    };
  }, []);

  return (
    <div className="public-frame">
      <header className="public-bar">
        <Link href="/" className="app-wordmark">
          <span>◩</span>
          <b>TRIMBIN</b>
        </Link>
        <nav>
          {LINKS.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              aria-current={pathname === href ? "page" : undefined}
            >
              {label}
            </Link>
          ))}
        </nav>
        {/* Signed in, the way back is the desk they were at. Signed out, the
            way in. Never both, and never neither. */}
        <Link className="primary small" href={identity ? "/home" : "/"}>
          {identity ? "Open Trimbin" : "Sign in"}
        </Link>
      </header>
      <div className="public-scroll">{children}</div>
    </div>
  );
}
