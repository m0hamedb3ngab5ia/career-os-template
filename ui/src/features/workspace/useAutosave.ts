import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiFetch } from "../../api/client";
import { errorText } from "../today/api";
import { draftUrl, type Doc, type Draft } from "./api";

export type SaveState = "saved" | "saving" | "error" | "conflict";  // conflict = 409: the server draft moved under us

/**
 * Draft autosave (TASK-033a): edits are debounced into one PUT carrying the last known `rev`; saves run one at a
 * time. Pending edits are flushed on unmount (in-app navigation) and on `pagehide` with a keepalive request
 * (sendBeacon can't carry the X-CareerOS write header or PUT). A failed save keeps the edit and stays in "error"
 * until a retry or the next edit succeeds: never silent data loss.
 */
export function useAutosave(rid: string, delay = 600) {
  const rev = useRef(0);
  const pending = useRef<Doc | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const inflight = useRef<Promise<boolean> | null>(null);
  const [state, setState] = useState<SaveState>("saved");
  const [error, setError] = useState("");
  const url = draftUrl(rid);

  /** Send the pending edit now. Resolves true when nothing is left unsaved. */
  const flush = useCallback(async (keepalive = false): Promise<boolean> => {
    clearTimeout(timer.current);
    while (inflight.current && !keepalive) await inflight.current;
    const doc = pending.current;
    if (!doc) return true;  // a failed save re-queues its doc, so nothing pending = nothing unsaved
    pending.current = null;
    const req = apiFetch<Draft>(url, {
      method: "PUT",
      keepalive,
      headers: { "X-CareerOS": "1", "Content-Type": "application/json" },
      // ponytail: unload can't await the in-flight save, so a keepalive PUT sent beside one assumes it commits first
      // (rev+1). Lost only if it commits second or fails; the older edit is never lost. No client-only fix exists.
      body: JSON.stringify({ rev: rev.current + (keepalive && inflight.current ? 1 : 0), resume: doc, author: "user" }),
    }).then(
      (d) => {
        rev.current = d.rev;
        if (!pending.current) setState("saved");
        return true;
      },
      (e: unknown) => {
        pending.current ??= doc;
        setError(errorText(e));
        setState(e instanceof ApiError && e.status === 409 ? "conflict" : "error");
        return false;
      },
    );
    const p = req.finally(() => {
      if (inflight.current === p) inflight.current = null;
    });
    inflight.current = p;
    return p;
  }, [url]);

  const flushRef = useRef(flush);
  flushRef.current = flush;

  const schedule = useCallback((doc: Doc) => {
    pending.current = doc;
    setState("saving");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => void flushRef.current(), delay);
  }, [delay]);

  useEffect(() => {
    const onHide = () => void flushRef.current(true);
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      void flushRef.current();  // leaving the page in-app: save what's pending
    };
  }, []);

  /** The server's draft moved (initial load, an accepted suggestion): later saves build on its rev. */
  const setRev = useCallback((n: number) => { rev.current = n; }, []);

  /** After a 409: take the server's draft (drops local edits). Resolves to it so the page can show it. */
  const reload = useCallback(async (): Promise<Draft> => {
    clearTimeout(timer.current);
    const d = await apiFetch<Draft>(url);
    pending.current = null;
    rev.current = d.rev;
    setState("saved");
    return d;
  }, [url]);

  /** After a 409: keep the local edit, adopt the server's rev, save again. */
  const overwrite = useCallback(async (): Promise<boolean> => {
    rev.current = (await apiFetch<Draft>(url)).rev;
    return flush();
  }, [url, flush]);

  // Closing the tab with an unsaved or failed edit: ask first (pagehide's keepalive PUT is best effort).
  useEffect(() => {
    if (state === "saved") return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [state]);

  return { state, error, schedule, flush, setRev, reload, overwrite };
}
