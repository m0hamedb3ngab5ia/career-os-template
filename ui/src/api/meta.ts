import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

// GET /api/meta (src/careeros/ui/services/meta.py): every code the UI renders plus the `ui:` settings.
export interface Meta {
  statuses: string[];
  tiers: string[];
  priorities: string[];
  action_types: string[];
  action_needs: string[];
  safety_verdicts: string[];
  stop_reasons: string[];
  clean_stops: string[];
  presets: { names: string[]; values: Record<string, Record<string, number>>; recommended: string; current: string };
  pipeline: { columns: { name: string; statuses: string[] }[]; closed: string[] };
  ui: { theme: string; undo_seconds: number; page_size: number };
}

export function useMeta() {
  return useQuery({
    queryKey: ["meta"],
    queryFn: () => apiFetch<Meta>("/api/meta"),
    staleTime: 5 * 60_000,
  });
}
