/**
 * Signing in, and holding onto who you are.
 *
 * Google Identity Services returns an ID token to the page rather than
 * redirecting through a callback. That is why the OAuth client needs no redirect
 * URI and no client secret: there is no server-side exchange, and a secret in a
 * page that anyone can view source on would not be one.
 *
 * The token lives in memory and in localStorage.
 *
 * sessionStorage was the first choice, on the reasoning that a token surviving a
 * closed tab also survives somebody walking away from a shared edit suite. That
 * reasoning cost more than it bought: sessionStorage is per-tab, so opening any
 * link in a new tab landed on a signed-out page, and the product read as one
 * that loses your session at random.
 *
 * The expiry is the control that actually matters, and it is enforced on every
 * read here and again on the server. Twelve hours, and a sign-out button that
 * clears it.
 */

const TOKEN_KEY = "trimbin.id_token";

export interface Identity {
  email: string;
  name: string;
  picture: string;
  /** Seconds since epoch. Google issues these for about an hour; ours last a
   *  working day. */
  expires_at: number;
  /** Present on a token this API minted. Cosmetic — the API re-derives the role
   *  from the roster on every request and never trusts what the page believed. */
  role?: string;
}

interface GoogleCredentialResponse {
  credential: string;
}

/** Set at build time from the same value Terraform gives the API. */
export const CLIENT_ID = process.env.NEXT_PUBLIC_OAUTH_CLIENT_ID ?? "";

let cached: { token: string; identity: Identity } | null = null;

/**
 * Read the claims without verifying them.
 *
 * Deliberately unverified, and safe because nothing here is a decision. The
 * page uses this to draw a name and know when to ask for a new token; every
 * answer that matters comes from the API, which verifies the signature properly
 * and does not care what the page believed.
 *
 * Two token shapes reach this. Google's is a JWT — header, payload, signature —
 * with the claims in the middle. Ours is payload and signature, with the claims
 * first, because there is no algorithm to negotiate when only one side ever
 * signs. Reading the middle of a two-part token gets the signature, which
 * base64-decodes to bytes that are not JSON, and the whole sign-in then fails
 * as "could not read that token" with nothing wrong anywhere.
 */
function claimsOf(token: string): Identity | null {
  const parts = token.split(".");
  const payload = parts.length >= 3 ? parts[1] : parts[0];
  try {
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const c = JSON.parse(json);
    if (!c.email) return null;
    return {
      email: String(c.email).toLowerCase(),
      name: c.name ?? c.email,
      picture: c.picture ?? "",
      expires_at: Number(c.exp ?? 0),
      role: c.role,
    };
  } catch {
    return null;
  }
}

/**
 * Sign in with a username and a password.
 *
 * This exists because an OAuth client can only be created by hand in a console,
 * and until somebody does that Google Sign-In cannot work at all. A deployment
 * with no second door is a deployment where the dashboard, the queue, every
 * override and every comment are built, shipped and unreachable.
 *
 * The token comes back signed by our own API and is held exactly like Google's.
 */
export async function signInWithPass(
  username: string,
  password: string,
): Promise<Identity> {
  const response = await fetch("/api/auth/pass", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => undefined);
    throw new Error(
      (body?.detail as string) ?? "That username and password did not match.",
    );
  }

  const body = await response.json();
  const identity = store(body.token as string);
  if (!identity)
    throw new Error("The server sent a token this page cannot read.");
  announce();
  return identity;
}

function store(token: string): Identity | null {
  const identity = claimsOf(token);
  if (!identity) return null;
  if (cached?.identity.email && cached.identity.email !== identity.email)
    clearUploadState();
  cached = { token, identity };
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Private browsing, or storage disabled. Sign-in still works for this page
    // load; it just will not survive a refresh.
  }
  return identity;
}

/** The signed-in identity, or null. Expired tokens count as signed out. */
export function currentIdentity(): Identity | null {
  if (!cached) {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem(TOKEN_KEY);
      // Anything left in the old place still counts, so nobody signed in
      // yesterday is signed out by this change.
      if (!saved) saved = sessionStorage.getItem(TOKEN_KEY);
    } catch {
      saved = null;
    }
    if (saved) store(saved);
  }
  if (!cached) return null;

  // Thirty seconds of slack. A token that expires mid-request produces a 401
  // the user reads as "it broke" rather than "sign in again".
  if (cached.identity.expires_at * 1000 < Date.now() + 30_000) {
    signOut();
    return null;
  }
  return cached.identity;
}

export function currentToken(): string | null {
  return currentIdentity() ? cached!.token : null;
}

/**
 * Tell the rest of the page that who is signed in has changed.
 *
 * The bar and every screen read the identity once on mount. Without a signal,
 * signing in from a panel in the header left the page it was drawn over still
 * showing its signed-out shape until a navigation.
 */
export function announce(): void {
  try {
    window.dispatchEvent(new CustomEvent("trimbin:auth"));
  } catch {
    /* not a browser */
  }
}

export function signOut(): void {
  cached = null;
  try {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    clearUploadState();
  } catch {
    /* nothing to clear */
  }
  try {
    // Other tabs of the same application, so signing out signs out everywhere
    // rather than only where the button was pressed.
    window.dispatchEvent(new CustomEvent("trimbin:auth"));
  } catch {
    /* not a browser */
  }
}

function clearUploadState(): void {
  if (typeof window === "undefined") return;
  const keys: string[] = [];
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (
      key?.startsWith("trimbin.upload.") ||
      key?.startsWith("trimbin.ingest.")
    )
      keys.push(key);
  }
  keys.forEach((key) => window.localStorage.removeItem(key));
  window.dispatchEvent(new CustomEvent("trimbin:upload-clear"));
}

/**
 * Load Google's script once and hand back the global it defines.
 *
 * Loaded on demand rather than in the document head: most visitors here never
 * sign in — the accuracy page and the demo are the point — and making them
 * fetch and run an auth SDK to read a page is a cost paid for nothing.
 */
let scriptLoading: Promise<void> | null = null;

function loadGoogleScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if ((window as any).google?.accounts?.id) return Promise.resolve();
  if (scriptLoading) return scriptLoading;

  scriptLoading = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not load Google sign-in."));
    document.head.appendChild(script);
  });
  return scriptLoading;
}

/**
 * Draw Google's own button into an element.
 *
 * Google's button rather than our own, and not for want of design opinions: a
 * sign-in button that does not look like the one people know is a sign-in
 * button people hesitate over, and Google's terms ask for it.
 */
export async function renderSignInButton(
  element: HTMLElement,
  onSignedIn: (identity: Identity) => void,
): Promise<void> {
  if (!CLIENT_ID) {
    // Said plainly rather than shown as a broken button. See
    // docs/oauth-client.md — this is the one value Terraform cannot create.
    element.textContent = "Sign-in is not configured on this deployment.";
    return;
  }

  await loadGoogleScript();
  const google = (window as any).google;

  google.accounts.id.initialize({
    client_id: CLIENT_ID,
    callback: (response: GoogleCredentialResponse) => {
      const identity = store(response.credential);
      if (identity) onSignedIn(identity);
    },
    // No automatic sign-in prompt. A page that asks who you are before you have
    // asked it for anything is a page people close.
    auto_select: false,
    cancel_on_tap_outside: true,
  });

  google.accounts.id.renderButton(element, {
    theme: "outline",
    size: "large",
    text: "signin_with",
    shape: "rectangular",
  });
}
