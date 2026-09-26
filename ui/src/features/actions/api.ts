import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type { ActionsView, BlockResult, GroupBy, NewItem, SafeResult, SortBy, Tab, WriteResult } from "./types";

export interface ActionsParams {
  tab: Tab;
  group: GroupBy;
  sort: SortBy;
}

function timeZone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return undefined;
  }
}

export function actionsUrl(p: ActionsParams): string {
  const q = new URLSearchParams({ tab: p.tab, group: p.group, sort: p.sort });
  const tz = timeZone();
  if (tz) q.set("tz", tz);
  return `/api/actions?${q}`;
}

export function useActions(p: ActionsParams) {
  return useQuery({
    queryKey: ["actions", p],
    queryFn: () => apiFetch<ActionsView>(actionsUrl(p)),
    placeholderData: (prev) => prev,
  });
}

/** Every Action Items write: invalidate the list, the sidebar counts and the board hints on success. */
function useWrite<TVars, TOut>(fn: (v: TVars) => Promise<TOut>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["actions"] });
      void qc.invalidateQueries({ queryKey: ["status"] });
      void qc.invalidateQueries({ queryKey: ["pipeline"] });
    },
  });
}

const enc = encodeURIComponent;

export function useMarkDone() {
  return useWrite((ids: string[]) =>
    ids.length === 1
      ? apiSend<WriteResult>("POST", `/api/actions/${enc(ids[0]!)}/done`)
      : apiSend<WriteResult>("POST", "/api/actions/bulk-done", { ids }),
  );
}

export function useReopen() {
  return useWrite((ids: string[]) =>
    ids.length === 1
      ? apiSend<WriteResult>("POST", `/api/actions/${enc(ids[0]!)}/reopen`)
      : apiSend<WriteResult>("POST", "/api/actions/bulk-reopen", { ids }),
  );
}

export function useSetDue() {
  return useWrite((v: { id: string; due: string | null; due_reason: string | null }) =>
    apiSend<WriteResult>("POST", `/api/actions/${enc(v.id)}/due`, { due: v.due, due_reason: v.due_reason }),
  );
}

export function useAddItem() {
  return useWrite((item: NewItem) => apiSend<{ id: string }>("POST", "/api/actions", item));
}

export function useBlockCompany() {
  return useWrite((id: string) => apiSend<BlockResult>("POST", `/api/actions/${enc(id)}/block-company`));
}

export function useUnblockCompany() {
  return useWrite((v: { id: string; company: string }) =>
    apiSend<unknown>("POST", `/api/actions/${enc(v.id)}/unblock-company`, { company: v.company }),
  );
}

export function useMarkSafe() {
  return useWrite((id: string) => apiSend<SafeResult>("POST", `/api/actions/${enc(id)}/mark-safe`));
}

export function useUndoMarkSafe() {
  return useWrite((v: { id: string; previous_status: string | null; registry_before: Record<string, unknown> | null }) =>
    apiSend<unknown>("POST", `/api/actions/${enc(v.id)}/mark-safe/undo`, {
      previous_status: v.previous_status,
      registry_before: v.registry_before,
    }),
  );
}
