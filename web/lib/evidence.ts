import { currentToken } from "./auth";

export type EvidenceItem = {
  id: string; source_id: string; start_us: number; end_us: number; kind: string;
  text: string; origin: string; decision: "accepted" | "uncertain" | "retracted";
  current: boolean; corrected?: boolean; selection_id?: string;
};
export type EvidenceRun = {
  id: string; task: string; mode: string; state: string; error_code: string | null;
  published: boolean;
};
export type Workspace = {
  revision: number; items: EvidenceItem[]; selections: EvidenceItem[];
  placements: Record<string, { scene: string; shot: string; take: string }>;
  analysis_mode: "fixture" | "nebius"; runs: EvidenceRun[];
};
export async function evidenceRequest<T>(path: string, body?: unknown): Promise<T> {
  const token = currentToken();
  const response = await fetch(`/api/evidence${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(response.status === 409
      ? "Workspace changed or search is still updating. Refresh and retry; your draft is retained."
      : typeof error.detail === "string" ? error.detail.replaceAll("_", " ") : `Request failed (${response.status})`);
  }
  return response.json();
}
