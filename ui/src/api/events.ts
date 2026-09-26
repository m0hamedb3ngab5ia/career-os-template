import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect, useState } from "react";

// Live updates from `careeros ui` (src/careeros/ui/routers/events.py): a named `hello` frame on every connect,
// then one named `changed` frame per re-indexed batch. The client marks the matching queries stale and
// TanStack Query refetches whatever is on screen. No polling.

export interface ChangedPayload {
  jobs?: string[];
  runs?: string[];
  actions?: boolean;
  config?: boolean;
  status?: boolean;
}

export type Connection = "connecting" | "open" | "reconnecting";

const BACKOFF_MS = [1000, 2000, 4000, 8000, 15000, 30000];

export function keysForChange(p: ChangedPayload): QueryKey[] {
  const keys: QueryKey[] = [];
  const add = (k: QueryKey) => {
    if (!keys.some((x) => JSON.stringify(x) === JSON.stringify(k))) keys.push(k);
  };
  if (p.jobs?.length) {
    add(["jobs"]);
    for (const id of p.jobs) add(["job", id]);
    add(["contacts"]); // contacts.json lives in the job folder
    add(["status"]);
  }
  if (p.runs?.length) {
    add(["runs"]);
    for (const id of p.runs) add(["run", id]);
    add(["status"]);
  }
  if (p.actions) {
    add(["status"]);
    add(["actions"]);
  }
  if (p.config) {
    add(["meta"]);
    add(["settings"]);
    add(["status"]);
  }
  if (p.status) add(["status"]);
  return keys;
}

function parse(data: unknown): ChangedPayload | null {
  if (typeof data !== "string") return null;
  try {
    const v: unknown = JSON.parse(data);
    return v && typeof v === "object" ? (v as ChangedPayload) : null;
  } catch {
    return null;
  }
}

/**
 * Subscribe once (in the app shell). While the browser retries on its own the state is "reconnecting"; if it
 * gives up (readyState CLOSED) we recreate the connection with backoff. Every `hello` after the first means we
 * may have missed changes, so all queries refetch.
 */
export function useLiveEvents(url = "/api/events"): Connection {
  const qc = useQueryClient();
  const [state, setState] = useState<Connection>("connecting");

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let hellos = 0;
    let stopped = false;

    function connect() {
      es = new EventSource(url);
      es.onopen = () => setState("open");
      es.addEventListener("hello", () => {
        attempt = 0;
        hellos += 1;
        setState("open");
        if (hellos > 1) void qc.invalidateQueries();
      });
      es.addEventListener("changed", (m) => {
        const p = parse((m as MessageEvent).data);
        if (!p) return;
        for (const queryKey of keysForChange(p)) void qc.invalidateQueries({ queryKey });
      });
      es.onerror = () => {
        setState("reconnecting");
        if (es?.readyState !== 2) return; // CONNECTING: the browser retries by itself
        es.close();
        const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)]!;
        attempt += 1;
        timer = setTimeout(() => {
          if (!stopped) connect();
        }, delay);
      };
    }

    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      es?.close();
    };
  }, [qc, url]);

  return state;
}
