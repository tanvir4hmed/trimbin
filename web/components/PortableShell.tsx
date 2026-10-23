"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut } from "@/lib/auth";

export function portablePath(path: string) {
  return path === "/studio" || /^\/projects\/[^/]+\/(media|evidence|timeline)$/.test(path);
}

export default function PortableShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const slug = pathname.match(/^\/projects\/([^/]+)\//)?.[1];
  return <><header style={{ padding: "1rem", borderBottom: "1px solid #555" }}>
    <nav aria-label="Editorial workflow" style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
      <Link href="/studio">Trimbin projects</Link>
      {slug && <><Link href={`/projects/${slug}/media`}>1. Media</Link>
        <Link href={`/projects/${slug}/evidence`}>2. Evidence & selections</Link>
        <Link href={`/projects/${slug}/timeline`}>3. Timeline & exports</Link></>}
      <button onClick={() => { signOut(); window.location.assign("/studio"); }}>Sign out</button>
    </nav>
  </header>{children}</>;
}
