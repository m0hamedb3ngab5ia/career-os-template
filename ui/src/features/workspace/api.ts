import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type { components } from "../../api/schema.gen";

type S = components["schemas"];
export type Draft = S["Draft"];
export type Annotation = S["Annotation"];
export type Published = S["Published"];
/** resume.json (schema v1, templates/resume/resume_schema.md); edited as plain JSON. */
export type Doc = Record<string, unknown>;

const base = (rid: string) => `/api/profile/resumes/${encodeURIComponent(rid)}`;
const ann = (rid: string, aid: string) => `${base(rid)}/annotations/${encodeURIComponent(aid)}`;
export const draftUrl = (rid: string) => `${base(rid)}/draft`;
export const wsKeys = { annotations: (rid: string) => ["workspace", rid, "annotations"] as const };

export const useDraft = (rid: string) =>
  useQuery({ queryKey: ["workspace", rid, "draft"], queryFn: () => apiFetch<Draft>(draftUrl(rid)), staleTime: Infinity, refetchOnMount: "always", refetchOnWindowFocus: false });
export const useAnnotations = (rid: string) =>
  useQuery({ queryKey: wsKeys.annotations(rid), queryFn: () => apiFetch<Annotation[]>(`${base(rid)}/annotations`) });

export const accept = (rid: string, aid: string) => apiSend<Draft>("POST", `${ann(rid, aid)}/accept`);
export const reject = (rid: string, aid: string) => apiSend<Annotation>("POST", `${ann(rid, aid)}/reject`);
export const reply = (rid: string, aid: string, text: string, apply: boolean) =>
  apiSend<Annotation>("POST", `${ann(rid, aid)}/replies`, { text, apply });
export const publish = (rid: string, key: string) => apiSend<Published>("POST", `${base(rid)}/publish`, { key });

/** One line of draft.changes.jsonl (DEC-015): `before`/`after` are nodes (bullet {id,text,..}) or plain values. */
export interface Change {
  id: string; at?: string | null; author: "ai" | "user"; target_id: string; kind?: string; op: "add" | "edit" | "delete";
  before?: unknown; after?: unknown; reverts?: string | null;
}
export const changesKey = (rid: string) => ["workspace", rid, "changes"] as const;
export const useChanges = (rid: string, enabled: boolean) =>
  useQuery({ queryKey: changesKey(rid), enabled, refetchOnMount: "always", queryFn: () => apiFetch<Change[]>(`${base(rid)}/draft/changes`) });
export const revertChange = (rid: string, cid: string) => apiSend<Draft>("POST", `${base(rid)}/draft/changes/${encodeURIComponent(cid)}/revert`);
