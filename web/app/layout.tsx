import type { Metadata } from "next";
import Link from "next/link";
import SignIn from "@/components/SignIn";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trimbin",
  description:
    "An assistant editor that never forgets. It organises a shoot day, surfaces only the shots that need a human eye, and remembers every take it passed over and why.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap"
        />
      </head>
      <body>
        <nav className="topbar">
          <Link href="/" className="logo">
            Trim<span>bin</span>
          </Link>
          {/* Every route here is reachable without an account. A system that
              publishes its own error rate should not put that behind a signup,
              and a visitor who has to register to look will not look. */}
          <div className="nav">
            <Link href="/">Overview</Link>
            <Link href="/accuracy">Accuracy</Link>
            <Link href="/project/1">Workspace</Link>
            <Link href="/sandbox">Try it</Link>
            <Link href="/demo">Status</Link>
          </div>
          {/* Appears only once there is something to sign in for, and renders
              nothing at all on a deployment without an OAuth client. */}
          <SignIn />
        </nav>
        {children}
      </body>
    </html>
  );
}
