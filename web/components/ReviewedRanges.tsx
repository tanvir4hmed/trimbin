"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AttemptItem } from "@/lib/api";

export default function ReviewedRanges({
  projectId,
  clipId,
  start,
  end,
  duration,
  canEdit,
  onSelect,
  candidate = false,
  onVerified,
  blockedRanges = [],
}: {
  projectId: number;
  clipId: string;
  start: number;
  end: number;
  duration: number;
  canEdit: boolean;
  onSelect: (start: number, end: number) => void;
  candidate?: boolean;
  onVerified?: (start: number, end: number) => void;
  blockedRanges?: { from: number; to: number }[];
}) {
  const cache = useQueryClient();
  const key = ["project", projectId, "attempts", clipId];
  const query = useQuery({
    queryKey: key,
    queryFn: () => api.attempts(projectId, clipId),
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [editingRevision, setEditingRevision] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [undo, setUndo] = useState<{
    rev: number;
    items: AttemptItem[];
  } | null>(null);
  const allItems = query.data?.items ?? [];
  // Older saves allowed the same clean interval to be appended repeatedly.
  // Keep the first record as the editable source of truth in this UI.
  const clean = allItems.filter(
    (row, index, rows) =>
      row.state === "clean" &&
      rows.findIndex(
        (candidate) =>
          candidate.state === "clean" &&
          Math.abs(candidate.start_s - row.start_s) < 0.001 &&
          Math.abs(candidate.end_s - row.end_s) < 0.001,
      ) === index,
  );
  async function commit(
    items: AttemptItem[],
    rev: number,
    options: { selectedId?: string | null; promote?: boolean } = {},
  ) {
    if (items.some((item) => blockedRanges.some(
      (blocked) => item.start_s < blocked.to && blocked.from < item.end_s,
    ))) {
      setMessage("A clean range overlaps an issue. Adjust it to the usable portion first.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const previous = query.data?.items ?? [];
      const next = await api.saveAttempts(projectId, clipId, {
        rev,
        command_id: crypto.randomUUID(),
        items,
      });
      cache.setQueryData(key, next);
      setUndo({ rev: next.rev, items: previous });
      setMessage("Reviewed ranges saved.");
      setSelected(options.selectedId ?? null);
      setEditingRevision(null);
      if (options.promote) onVerified?.(start, end);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not save reviewed ranges.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="reviewed-ranges">
      <h3>Reviewed clean ranges</h3>
      <p className="policy-note">
        Your review of this source. Edit In / Out above, then save. Shot
        selections are separate.
      </p>
      {clean.map((row) => (
        <div className="reviewed-range" key={row.id}>
          <button
            aria-pressed={selected === row.id}
            onClick={() => {
              setSelected(row.id);
              setEditingRevision(query.data?.rev ?? null);
              onSelect(row.start_s, row.end_s);
            }}
          >
            {row.start_s.toFixed(2)}–{row.end_s.toFixed(2)} s · Clean · Reviewed
          </button>
          <button
            disabled={!canEdit || busy}
            onClick={() =>
              query.data &&
              void commit(
                query.data.items.filter(
                  (item) =>
                    item.id !== row.id &&
                    !(
                      item.state === "clean" &&
                      Math.abs(item.start_s - row.start_s) < 0.001 &&
                      Math.abs(item.end_s - row.end_s) < 0.001
                    ),
                ),
                query.data.rev,
              )
            }
          >
            Withdraw
          </button>
        </div>
      ))}
      <button
        disabled={
          !canEdit ||
          busy ||
          !query.data ||
          !(start >= 0 && end > start && end <= duration)
        }
        onClick={() => {
          if (!query.data) return;
          if (selected && editingRevision !== query.data.rev) {
            setMessage(
              "These ranges changed while you were editing. Cancel and select the range again to review the latest version.",
            );
            return;
          }
          const existing = clean.find(
            (item) =>
              Math.abs(item.start_s - start) < 0.001 &&
              Math.abs(item.end_s - end) < 0.001,
          );
          if (!selected && existing) {
            setSelected(existing.id);
            setEditingRevision(query.data.rev);
            setMessage("This clean range is already reviewed.");
            if (candidate) onVerified?.(start, end);
            return;
          }
          const row: AttemptItem = {
            id: selected ?? crypto.randomUUID(),
            label: "Reviewed clean range",
            start_s: start,
            end_s: end,
            state: "clean",
            note: "Human-reviewed source range",
          };
          void commit(
            selected
              ? query.data.items.map((item) =>
                  item.id === selected
                    ? { ...item, start_s: start, end_s: end }
                    : item,
                )
              : [...query.data.items, row],
            query.data.rev,
            { selectedId: row.id, promote: candidate },
          );
        }}
      >
        {selected ? "Save adjusted clean range" : candidate ? "Verify clean" : "Mark range reviewed clean"}
      </button>
      {selected && (
        <button
          onClick={() => {
            const original = query.data?.items.find(
              (item) => item.id === selected,
            );
            if (original) onSelect(original.start_s, original.end_s);
            setSelected(null);
            setEditingRevision(null);
          }}
        >
          Cancel adjustment
        </button>
      )}
      {undo && (
        <button
          disabled={busy || query.data?.rev !== undo.rev}
          onClick={() => void commit(undo.items, undo.rev)}
        >
          Undo last range change
        </button>
      )}
      {(message || query.error) && (
        <p role="status">{message || query.error?.message}</p>
      )}
    </section>
  );
}
