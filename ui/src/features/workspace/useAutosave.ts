import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "../../api/client";
import { errorText } from "../today/api";
import { draftUrl, type Doc, type Draft } from "./api";

export type SaveState = "saved" | "saving" | "error";

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
      body: JSON.stringify({ rev: rev.current, resume: doc, author: "user" }),
    }).then(
      (d) => {
        rev.current = d.rev;
        if (!pending.current) setState("saved");
        return true;
      },
      (e: unknown) => {
        pending.current ??= doc;
        setError(errorText(e));
        setState("error");
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

  return { state, error, schedule, flush, setRev };
}
