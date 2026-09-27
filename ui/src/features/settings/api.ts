import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type {
  Advice,
  PrunePlan,
  RankingPreview,
  SectionData,
  SectionSummary,
  StorageData,
  Values,
} from "./types";

// Query keys: ["settings", ...] refetch on SSE `changed {config}`; ["storage"] and ["advise"] on runs and
// config changes (ui/src/api/events.ts).

export function useSectionList() {
  return useQuery({
    queryKey: ["settings", "list"],
    queryFn: () => apiFetch<{ sections: SectionSummary[] }>("/api/settings"),
    staleTime: Infinity,
  });
}

export function useSection(id: string) {
  return useQuery({
    queryKey: ["settings", "section", id],
    queryFn: () => apiFetch<SectionData>(`/api/settings/${encodeURIComponent(id)}`),
    retry: false,
  });
}

export function useDiff(section: string) {
  return useMutation({
    mutationFn: (changes: Values) =>
      apiSend<{ diffs: Record<string, string> }>("POST", `/api/settings/${encodeURIComponent(section)}/diff`, {
        changes,
      }),
  });
}

export function useSave(section: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ changes, version }: { changes: Values; version?: string }) =>
      apiSend<{ old: Values; version: string }>("PUT", `/api/settings/${encodeURIComponent(section)}`, {
        changes,
        version,
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["settings", "section", section] });
      void qc.invalidateQueries({ queryKey: ["meta"] });
      void qc.invalidateQueries({ queryKey: ["advise"] });
      void qc.invalidateQueries({ queryKey: ["storage"] });
    },
  });
}

export function useResetGroup(section: string) {
  return useMutation({
    mutationFn: (group: string) =>
      apiSend<{ changes: Values }>(
        "POST",
        `/api/settings/${encodeURIComponent(section)}/reset/${encodeURIComponent(group)}`,
      ),
  });
}

export function useRankingPreview(kind: "score" | "prepare", weights: Record<string, number>, enabled: boolean) {
  return useQuery({
    queryKey: ["settings", "ranking-preview", kind, weights],
    queryFn: () => apiSend<RankingPreview>("POST", "/api/settings/runs/ranking-preview", { kind, weights }),
    enabled,
    placeholderData: (prev) => prev,
    retry: false,
  });
}

export function useStorage() {
  return useQuery({ queryKey: ["storage"], queryFn: () => apiFetch<StorageData>("/api/storage") });
}

export function useAdvice() {
  return useQuery({ queryKey: ["advise"], queryFn: () => apiFetch<Advice>("/api/advise") });
}

export function useApplyAdvice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiSend<{ id: string; path: string; from: unknown; to: unknown }>(
        "POST",
        `/api/advise/${encodeURIComponent(id)}/apply`,
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["advise"] });
      void qc.invalidateQueries({ queryKey: ["settings"] });
      void qc.invalidateQueries({ queryKey: ["storage"] });
    },
  });
}

export function usePrunePlan() {
  return useMutation({ mutationFn: () => apiSend<PrunePlan>("POST", "/api/prune", { dry_run: true }) });
}

export function usePruneStart() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiSend<{ kind: string; started: boolean; pid: number }>("POST", "/api/prune", { dry_run: false }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["runs"] }),
  });
}
