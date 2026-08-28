import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8080";

const config: NextConfig = {
  // A container, not a static export: the accuracy page reads live data on
  // every request and a prerendered build would be a screenshot with extra
  // steps.
  output: "standalone",

  // The browser calls same-origin and Next forwards to the API. Two benefits:
  // no CORS preflight on every request, and the API's address is not baked into
  // client code where changing it means a rebuild.
  async rewrites() {
    return [
      { source: "/public/:path*", destination: `${API_URL}/public/:path*` },
      { source: "/projects/:path*", destination: `${API_URL}/projects/:path*` },
      { source: "/uploads/:path*", destination: `${API_URL}/uploads/:path*` },
    ];
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
