"use client";

/**
 * Getting in.
 *
 * Two doors, and the panel asks the API which are open rather than assuming.
 * Offering Google on a deployment with no OAuth client draws a button that does
 * nothing; hiding the password form on a deployment that has one leaves a door
 * nobody finds. Both failures look like the product being broken, and one of
 * them was: every screen behind sign-in shipped and stayed unreachable, because
 * an OAuth client is the one thing here that no API can create.
 *
 * One form for both kinds of person. An editor types their address and their
 * own password; a guest types the name they want their decisions recorded
 * against and the shared one. The API decides which happened — the page never
 * needs to know before asking.
 */

import { useEffect, useRef, useState } from "react";
import { CLIENT_ID, Identity, renderSignInButton, signInWithPass } from "@/lib/auth";
import { api } from "@/lib/api";

interface Options {
  google: boolean;
  password: boolean;
}

export default function SignInPanel({
  onSignedIn,
}: {
  onSignedIn: (who: Identity) => void;
}) {
  const [options, setOptions] = useState<Options | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void api
      .authOptions()
      .then(setOptions)
      // Assume neither rather than both. A panel offering a door that is not
      // there is worse than one saying it could not ask.
      .catch(() => setOptions({ google: false, password: false }));
  }, []);

  useEffect(() => {
    if (!options?.google || !CLIENT_ID || !buttonRef.current) return;
    void renderSignInButton(buttonRef.current, onSignedIn);
  }, [options, onSignedIn]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await signInWithPass(username.trim(), password));
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "That username and password did not match.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (!options) return <p className="waiting">Checking how to sign you in…</p>;

  if (!options.google && !options.password) {
    return (
      <p className="hint">
        No sign-in method is configured on this deployment. See
        docs/oauth-client.md, or set a session secret and a password.
      </p>
    );
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
        <form
          className="pass-form"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <label>
            Username
            <input
              type="text"
              value={username}
              maxLength={80}
              autoComplete="username"
              placeholder="your name, or your editor address"
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              maxLength={200}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>

          <button
            type="submit"
            className="primary"
            disabled={busy || password.length === 0 || username.trim().length === 0}
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>

          {error && <p className="error small">{error}</p>}

          {/* Said before they type it, not after they lose work. For a guest the
              username is the identity: it is what the archive records against
              every call they make, and typing the same one tomorrow is what
              brings them back to their own projects. */}
          <p className="hint small">
            Signing in as a guest? Your username is your identity here — every
            decision you make is recorded against it, and typing the same one
            tomorrow brings you back to your own projects.
          </p>
        </form>
      )}
    </div>
  );
}
