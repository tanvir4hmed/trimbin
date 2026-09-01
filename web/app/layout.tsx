import type { Metadata } from "next";
import AppBar from "@/components/AppBar";
import Providers from "@/components/Providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trimbin",
  description:
    "Post-production triage. Every take measured, compared within its shot, and the reason kept.",
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
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap"
        />
      </head>
      <body>
        <Providers>
          {/* One bar, both states. A visitor who signs in finds the same
              product with more of it available, rather than being moved to
              another one. */}
          <AppBar />
          {children}
        </Providers>
      </body>
    </html>
  );
}
