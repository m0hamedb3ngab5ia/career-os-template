import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect, useState } from "react";

// The server pushes one small event per change (`{type, id?}`) on /api/events after re-indexing; the client
// marks the matching queries stale and TanStack Query refetches whatever is on screen. No polling.

export interface LiveEvent {
  type: string;
  id?: string;
}

export type Connection = "connecting" | "open" | "reconnecting";

export function keysForEvent(e: LiveEvent): QueryKey[] {
  switch (e.type) {
    case "job":
      return e.id ? [["jobs"], ["job", e.id], ["status"]] : [["jobs"], ["status"]];
    case "run":
      return [["runs"], ["status"]];
    case "action":
      return [["actions"], ["status"]];
    case "contact":
      return [["contacts"]];
    case "settings":
      return [["settings"], ["meta"], ["status"]];
    case "storage":
      return [["storage"]];
    case "reindex":
      return [[]];
    default:
      return [["status"]];
  }
}

function parseEvent(data: unknown): LiveEvent | null {
  if (typeof data !== "string") return null;
  try {
    const v: unknown = JSON.parse(data);
    if (v && typeof v === "object" && typeof (v as LiveEvent).type === "string") return v as LiveEvent;
  } catch {
    /* not JSON: ignore */
  }
  return null;
}

/** Subscribe once (in the app shell). EventSource reconnects by itself; we only report the state. */
export function useLiveEvents(url = "/api/events"): Connection {
  const qc = useQueryClient();
  const [state, setState] = useState<Connection>("connecting");

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const es = new EventSource(url);
    es.onopen = () => setState("open");
    es.onerror = () => setState("reconnecting");
    es.onmessage = (m) => {
      const e = parseEvent(m.data);
      if (!e) return;
      for (const queryKey of keysForEvent(e)) void qc.invalidateQueries({ queryKey });
    };
    return () => es.close();
  }, [qc, url]);

  return state;
}
