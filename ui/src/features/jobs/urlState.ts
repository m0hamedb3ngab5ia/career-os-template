import { useCallback } from "react";
import { useSearchParams } from "react-router";
import type { TabKey } from "./types";

// Jobs view state lives in the query string (docs/UI.md "URL state"):
//   ?tab=active|review|applied|tier_a|all  &q=<search>  &sort=[-]fit|company|…  &cols=<hidden column keys>
//   &sel=<selected job ids>
// Defaults are left out so /jobs stays clean.

export const TABS: TabKey[] = ["active", "review", "applied", "tier_a", "all"];
export const DEFAULT_TAB: TabKey = "active";
export const SORT_KEYS = ["fit", "company", "status", "tier", "found_at", "applied_at", "updated_at"] as const;
export type SortKey = (typeof SORT_KEYS)[number];
export const DEFAULT_SORT = "-fit";
/** Columns the chooser can hide (the checkbox and Company always show). */
export const HIDEABLE = ["role", "tier", "fit", "status", "safety", "qa", "ats", "found", "applied", "next"] as const;

export interface JobsView {
  tab: TabKey;
  q: string;
  sort: string;
  hidden: string[];
  selected: string[];
}

function list(v: string | null): string[] {
  return v ? v.split(",").filter(Boolean) : [];
}

function validSort(s: string | null): string {
  if (!s) return DEFAULT_SORT;
  return (SORT_KEYS as readonly string[]).includes(s.replace(/^-/, "")) ? s : DEFAULT_SORT;
}

export function readView(p: URLSearchParams): JobsView {
  const tab = p.get("tab");
  return {
    tab: (TABS as string[]).includes(tab ?? "") ? (tab as TabKey) : DEFAULT_TAB,
    q: p.get("q") ?? "",
    sort: validSort(p.get("sort")),
    hidden: list(p.get("cols")).filter((c) => (HIDEABLE as readonly string[]).includes(c)),
    selected: list(p.get("sel")),
  };
}

export function writeView(p: URLSearchParams, patch: Partial<JobsView>): URLSearchParams {
  const next = new URLSearchParams(p);
  const set = (k: string, v: string, dflt = "") => (v && v !== dflt ? next.set(k, v) : next.delete(k));
  if (patch.tab !== undefined) set("tab", patch.tab, DEFAULT_TAB);
  if (patch.q !== undefined) set("q", patch.q.trim());
  if (patch.sort !== undefined) set("sort", patch.sort, DEFAULT_SORT);
  if (patch.hidden !== undefined) set("cols", patch.hidden.join(","));
  if (patch.selected !== undefined) set("sel", patch.selected.join(","));
  return next;
}

/** Numbers and dates read best biggest/newest first; names and codes A to Z. */
const DESC_FIRST = new Set(["fit", "found_at", "applied_at", "updated_at"]);

export function toggleSort(current: string, key: SortKey): string {
  const col = current.replace(/^-/, "");
  if (col === key) return current.startsWith("-") ? key : `-${key}`;
  return DESC_FIRST.has(key) ? `-${key}` : key;
}

const SORT_NAMES: Record<string, string> = {
  fit: "fit",
  company: "company",
  status: "status",
  tier: "tier",
  found_at: "found date",
  applied_at: "applied date",
  updated_at: "last update",
};

/** "highest first", "A to Z", "newest first". */
export function sortDirection(sort: string): string {
  const desc = sort.startsWith("-");
  const col = sort.replace(/^-/, "");
  return col === "fit"
      ? desc ? "highest first" : "lowest first"
      : DESC_FIRST.has(col)
        ? desc ? "newest first" : "oldest first"
        : col === "tier"
          ? desc ? "C to A" : "A to C"
          : desc ? "Z to A" : "A to Z";
}

export function sortCaption(sort: string): string {
  const col = sort.replace(/^-/, "");
  return `sorted by ${SORT_NAMES[col] ?? col}, ${sortDirection(sort)}`;
}

export function useJobsView() {
  const [params, setParams] = useSearchParams();
  const view = readView(params);
  // Selection and typing replace the history entry; tab, sort and columns are real navigation steps.
  const update = useCallback(
    (patch: Partial<JobsView>, replace = false) => setParams((p) => writeView(p, patch), { replace }),
    [setParams],
  );
  return [view, update] as const;
}
