/**
 * Signing in, and holding onto who you are.
 *
 * Google Identity Services returns an ID token to the page rather than
 * redirecting through a callback. That is why the OAuth client needs no redirect
 * URI and no client secret: there is no server-side exchange, and a secret in a
 * page that anyone can view source on would not be one.
 *
 * The token lives in memory and in sessionStorage — not localStorage. A token
 * that survives closing the tab is a token that survives someone walking away
 * from a shared edit suite, and these are hour-long credentials with somebody's
 * unreleased footage behind them.
 */

const TOKEN_KEY = "trimbin.id_token";

export interface Identity {
  email: string;
  name: string;
  picture: string;
  /** Seconds since epoch. Google issues these for about an hour. */
  expires_at: number;
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
 */
function claimsOf(token: string): Identity | null {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const c = JSON.parse(json);
    if (!c.email) return null;
    return {
      email: String(c.email).toLowerCase(),
      name: c.name ?? c.email,
      picture: c.picture ?? "",
      expires_at: Number(c.exp ?? 0),
    };
  } catch {
    return null;
  }
}

function store(token: string): Identity | null {
  const identity = claimsOf(token);
  if (!identity) return null;
  cached = { token, identity };
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Private browsing, or storage disabled. Sign-in still works for this
    // page load; it just will not survive a refresh.
  }
  return identity;
}

/** The signed-in identity, or null. Expired tokens count as signed out. */
export function currentIdentity(): Identity | null {
  if (!cached) {
    let saved: string | null = null;
    try {
      saved = sessionStorage.getItem(TOKEN_KEY);
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

export function signOut(): void {
  cached = null;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* nothing to clear */
  }
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
