"use client";

import { useEffect, useRef, useState } from "react";

export default function EntityMenu({
  kind,
  name,
  onRename,
  children,
}: {
  kind: string;
  name: string;
  onRename: (name: string) => Promise<unknown>;
  children?: React.ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const menu = useRef<HTMLDetailsElement>(null);
  const [draft, setDraft] = useState(name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (menu.current && !menu.current.contains(event.target as Node))
        menu.current.open = false;
    };
    const closeEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && menu.current) menu.current.open = false;
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeEscape);
    };
  }, []);
  return (
    <>
      <details ref={menu} className="entity-menu">
        <summary aria-label={`${kind} actions`} title={`${kind} actions`}>
          ⋯
        </summary>
        <div className="entity-menu-items">
          <button
            onClick={() => {
              setDraft(name);
              setError("");
              if (menu.current) menu.current.open = false;
              dialog.current?.showModal();
            }}
          >
            Rename {kind.toLowerCase()}
          </button>
          {children}
        </div>
      </details>
      <dialog
        className="rename-dialog"
        ref={dialog}
        onCancel={(event) => {
          if (busy) event.preventDefault();
        }}
      >
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (!draft.trim() || busy) return;
            setBusy(true);
            setError("");
            try {
              await onRename(draft.trim());
              dialog.current?.close();
            } catch (error) {
              setError(
                error instanceof Error ? error.message : "Could not rename.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          <h2>Rename {kind.toLowerCase()}</h2>
          <label>
            Name
            <input
              autoFocus
              value={draft}
              maxLength={200}
              required
              disabled={busy}
              onChange={(event) => setDraft(event.target.value)}
            />
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <footer>
            <button
              type="button"
              disabled={busy}
              onClick={() => dialog.current?.close()}
            >
              Cancel
            </button>
            <button className="primary" disabled={busy || !draft.trim()}>
              {busy ? "Saving…" : "Save"}
            </button>
          </footer>
        </form>
      </dialog>
    </>
  );
}
