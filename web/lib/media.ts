import { currentToken } from "./auth";
import type { components } from "./schema";

export type MediaSource = components["schemas"]["MediaSourceView"];
export type MediaUpload = components["schemas"]["MediaUploadView"];

export async function mediaRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = currentToken();
  const response = await fetch(`/api/media-library${path}`, {
    ...init,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(typeof init.body === "string" ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail.replaceAll("_", " ") : `Request failed (${response.status})`);
  }
  return response.status === 204 ? undefined as T : response.json();
}

export function uploadIdentity(project: number, file: File): string {
  return `trimbin.media-upload.${project}.${file.name}.${file.size}.${file.lastModified}`;
}

async function hash(data: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await data.arrayBuffer());
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

/** Reselecting a File after reload never trusts only its name/size/mtime. */
export async function verifyUploadPrefix(file: File, session: MediaUpload): Promise<void> {
  const size = session.chunk_bytes ?? 8 * 1024 * 1024;
  if (file.size !== session.expected_bytes) throw new Error("Choose the same original file to resume.");
  for (let index = 0; index < session.chunk_hashes.length; index++) {
    const actual = await hash(file.slice(index * size, Math.min((index + 1) * size, file.size)));
    if (actual !== session.chunk_hashes[index]) {
      throw new Error("This file differs from the uploaded bytes. Choose the original file or discard the pending upload.");
    }
  }
}
