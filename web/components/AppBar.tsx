"use client";

/**
 * The bar across the top of the application.
 *
 * Two states rather than two designs. Signed out it offers the way in; signed
 * in it offers the four places there are to be. The same bar either way, because
 * a visitor who signs in should find themselves in the same product with more
 * of it available — not moved to a different one.
 *
 * What is *not* here is a second navigation for guests. One interface,
 * permissions changing what is possible and never what is visible: a guest sees
 * the upload button on our projects and is told why it is off, rather than
 * being sent somewhere the real users never go.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Me } from "@/lib/api";
import { api } from "@/lib/api";
import {
  CLIENT_ID,
  Identity,
  currentIdentity,
  renderSignInButton,
  signOut,
} from "@/lib/auth";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/projects", label: "Projects" },
  { href: "/archive", label: "Archive" },
  { href: "/accuracy", label: "Accuracy" },
] as const;

export default function AppBar() {
  const pathname = usePathname();
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const buttonRef = useRef<HTMLDivElement>(null);

  // Read the stored session on mount rather than during render. sessionStorage
  // does not exist while Next renders on the server, and reaching for it there
  // makes the first paint disagree with the second.
  useEffect(() => {
    setIdentity(currentIdentity());
  }, []);

  const loadMe = useCallback(async () => {
    try {
      setMe(await api.me());
    } catch {
      // Not fatal. The bar draws its signed-out shape, which is correct for
      // somebody the API could not identify anyway.
      setMe(null);
    }
  }, []);

  useEffect(() => {
    void loadMe();
  }, [identity, loadMe]);

  useEffect(() => {
    if (identity || !buttonRef.current) return;
    void renderSignInButton(buttonRef.current, (who) => setIdentity(who));
  }, [identity]);

  // Close the overflow menu when the route changes. A menu that survives
  // navigation covers the page somebody just asked for.
  useEffect(() => setMenuOpen(false), [pathname]);

  const active = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  return (
    <nav className="topbar">
      <Link href={identity ? "/dashboard" : "/"} className="logo">
        Trim<span>bin</span>
      </Link>

      {identity && (
        <div className="nav">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              aria-current={active(l.href) ? "page" : undefined}
            >
              {l.label}
            </Link>
          ))}
        </div>
      )}

      <div className="bar-right">
        {/* The role, said out loud. A guest who can overrule our calls should
            know that is deliberate rather than wondering whether they are about
            to break something. */}
        {identity && me?.role && (
          <span className={`role-chip ${me.role}`} title={me.email ?? ""}>
            {me.role === "lead" ? "lead editor" : me.role}
          </span>
        )}

        <div className="overflow">
          <button
            type="button"
            className="overflow-toggle"
            onClick={() => setMenuOpen((v) => !v)}
            aria-expanded={menuOpen}
            aria-label="More"
          >
            ⋯
          </button>
          {menuOpen && (
            <div className="overflow-menu" role="menu">
              <Link href="/about" role="menuitem">
                About Trimbin
              </Link>
              <Link href="/guide" role="menuitem">
                How to use it
              </Link>
              <Link href="/accuracy" role="menuitem">
                How often it is right
              </Link>
              {/* What is running and what is not earned yet. Reachable rather
                  than buried: a status page nobody can find is the same as one
                  that omits things. */}
              <Link href="/demo" role="menuitem">
                What is built, and what is not
              </Link>
              {!identity && (
                <Link href="/project/1" role="menuitem">
                  Look at a real project
                </Link>
              )}
            </div>
          )}
        </div>

        {!identity && CLIENT_ID && <div className="signin" ref={buttonRef} />}
        {!identity && !CLIENT_ID && (
          // Said plainly rather than shown as a button that cannot work.
          // See docs/oauth-client.md — the one value Terraform cannot create.
          <span className="hint small">Sign-in is not configured here.</span>
        )}

        {identity && (
          <button
            type="button"
            className="signout"
            onClick={() => {
              signOut();
              setIdentity(null);
              setMe(null);
            }}
            title={identity.email}
          >
            {identity.name.split(" ")[0]} · sign out
          </button>
        )}
      </div>
    </nav>
  );
}
