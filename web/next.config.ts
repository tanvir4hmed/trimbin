import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8080";

const config: NextConfig = {
  // A container, not a static export: the accuracy page reads live data on
  // every request and a prerendered build would be a screenshot with extra
  // steps.
  output: "standalone",

  // For local development only.
  //
  // In production the load balancer routes /api/* to the API and strips the
  // prefix before Next sees it, so this never fires. Running `next dev` there is
  // no load balancer, and this makes the same URLs work.
  //
  // Deliberately not the production path: proxying every API call through the
  // Next container adds a hop and its own fetch timeout, which a cold-starting
  // API can exceed — and did.
  // Every address this application ever published keeps working.
  //
  // The scheme changed — `/project/6?scene=1&shot=1` became
  // `/projects/kill-bill-6/scenes/1/shots/1`, `/archive` became `/search`,
  // `/dashboard` became `/home` — and a link somebody bookmarked or pasted
  // into a message should not die because we renamed a route. `/projects/6`
  // still resolves too: only the trailing number in a slug is read, so the
  // old id-only form is a valid slug.
  async redirects() {
    return [
      { source: "/dashboard", destination: "/home", permanent: true },
      { source: "/archive", destination: "/search", permanent: true },
      // The shot and scene used to be query parameters, and Next cannot read
      // those in a redirect rule — so the project page itself forwards them,
      // and these cover the path forms.
      {
        source: "/project/:id/scene/:scene",
        destination: "/projects/:id/scenes/:scene/coverage",
        permanent: true,
      },
      { source: "/project/:id/ingest", destination: "/projects/:id/ingest", permanent: true },
      { source: "/project/:id", destination: "/projects/:id", permanent: true },
    ];
  },

  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // The site frames nothing and should be framed by nothing.
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },

  eslint: {
    // Lint runs in CI as its own step. Failing a production build on a style
    // rule takes the site down for something that is not a fault.
    ignoreDuringBuilds: true,
  },
};

export default config;
