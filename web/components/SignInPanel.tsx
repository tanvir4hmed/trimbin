"use client";

/**
 * Signing in.
 *
 * One form for both kinds of person: an editor types their address and their own
 * password, a guest types a name and the shared one. The API decides which
 * happened.
 *
 * The guest credentials are printed under the form. A trial whose password lives
 * in a README is a trial nobody reaches, and hiding a value the page hands out
 * on request is theatre.
 */

import { useEffect, useRef, useState } from "react";
import { CLIENT_ID, Identity, renderSignInButton, signInWithPass } from "@/lib/auth";
import { api } from "@/lib/api";

interface Options {
  google: boolean;
  password: boolean;
}

/** Shown on the form. Not a secret — a guest can read, comment and overrule, and
 *  can neither upload into our productions nor run the panel on them. */
const TRIAL_PASS = process.env.NEXT_PUBLIC_TRIAL_PASS ?? "";
const TRIAL_USER = "Guest";

export default function SignInPanel({
  onSignedIn,
  showTrial = true,
}: {
  onSignedIn: (who: Identity) => void;
  showTrial?: boolean;
}) {
  const [options, setOptions] = useState<Options | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void api
      .authOptions()
      .then(setOptions)
      .catch(() => setOptions({ google: false, password: false }));
  }, []);

  useEffect(() => {
    if (!options?.google || !CLIENT_ID || !buttonRef.current) return;
    void renderSignInButton(buttonRef.current, onSignedIn);
  }, [options, onSignedIn]);

  const submit = async (user: string, pass: string) => {
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await signInWithPass(user.trim(), pass));
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "That username and password did not match.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (!options) return <p className="waiting">Loading.</p>;

  if (!options.google && !options.password) {
    return <p className="hint">Sign-in is not configured on this deployment.</p>;
  }

  return (
    <div className="signin-panel">
      {options.google && CLIENT_ID && (
        <>
          <div className="signin big" ref={buttonRef} />
          {options.password && <p className="or">or</p>}
        </>
      )}

      {options.password && (
        <>
          <form
            className="pass-form"
            onSubmit={(e) => {
              e.preventDefault();
              void submit(username, password);
            }}
          >
            <label>
              Username
              <input
                type="text"
                value={username}
                maxLength={80}
                autoComplete="username"
                placeholder="your name"
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>

            <label>
              Password
              <span className="with-reveal">
                <input
                  type={reveal ? "text" : "password"}
                  value={password}
                  maxLength={200}
                  autoComplete="current-password"
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="reveal"
                  onClick={() => setReveal((v) => !v)}
                  aria-label={reveal ? "Hide password" : "Show password"}
                >
                  {reveal ? "hide" : "show"}
                </button>
              </span>
            </label>

            <button
              type="submit"
              className="primary"
              disabled={busy || password.length === 0 || username.trim().length === 0}
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>

            {error && <p className="error small">{error}</p>}
          </form>

          {showTrial && TRIAL_PASS && (
            <div className="trial">
              <button
                type="button"
                className="try-it"
                onClick={() => {
                  setUsername(TRIAL_USER);
                  setPassword(TRIAL_PASS);
                  setReveal(true);
                  void submit(TRIAL_USER, TRIAL_PASS);
                }}
              >
                Try it as a guest
              </button>
              <dl className="creds">
                <div>
                  <dt>User</dt>
                  <dd className="mono">{TRIAL_USER}</dd>
                </div>
                <div>
                  <dt>Password</dt>
                  <dd className="mono">{TRIAL_PASS}</dd>
                </div>
              </dl>
            </div>
          )}
        </>
      )}
    </div>
  );
}
