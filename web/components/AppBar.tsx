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
import { useCallback, useEffect, useState } from "react";
import SignInPanel from "@/components/SignInPanel";
import type { Me } from "@/lib/api";
import { api } from "@/lib/api";
import { Identity, currentIdentity, signOut } from "@/lib/auth";

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
  const [signingIn, setSigningIn] = useState(false);

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

  // Close the menus when the route changes. A panel that survives navigation
  // covers the page somebody just asked for.
  useEffect(() => {
    setMenuOpen(false);
    setSigningIn(false);
  }, [pathname]);

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

        {!identity && (
          <div className="overflow">
            <button
              type="button"
              className="primary small"
              onClick={() => setSigningIn((v) => !v)}
              aria-expanded={signingIn}
            >
              Sign in
            </button>
            {signingIn && (
              <div className="overflow-menu wide">
                <SignInPanel
                  onSignedIn={(who) => {
                    setIdentity(who);
                    setSigningIn(false);
                  }}
                />
              </div>
            )}
          </div>
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
