import { useCallback } from "react";
import { useSearchParams } from "react-router";
import type { TabKey } from "./types";

// Jobs view state lives in the query string (docs/UI.md "URL state"):
//   ?tab=active|review|applied|tier_a|all  &q=<search>  &loc=<location contains>  &sort=[-]fit|company|…
//   &cols=<hidden column keys>  &sel=<selected job ids>
//   &f.<field>=v1,v2 (column value filter; each value URI-encoded so commas survive)  &f.<field>=min..max (number
//   or ISO date range, either side may be empty). Fields: see FILTERS.
// Defaults are left out so /jobs stays clean.

export const TABS: TabKey[] = ["active", "review", "applied", "tier_a", "all"];
export const DEFAULT_TAB: TabKey = "active";
export const SORT_KEYS = ["fit", "company", "location", "status", "tier", "found_at", "applied_at", "updated_at"] as const;
export type SortKey = (typeof SORT_KEYS)[number];
export const DEFAULT_SORT = "-fit";
/** Columns the chooser can hide (the checkbox and Company always show). */
export const HIDEABLE = ["role", "location", "tier", "fit", "status", "safety", "qa", "ats", "found", "applied", "next"] as const;

/** Column filters (docs/UI.md "Jobs"): value lists, and min..max ranges on numbers and ISO dates. `param` is
 *  the API query key when it differs from the field (exact locations vs the `location` substring search). */
export const FILTERS = {
  company: { kind: "values" },
  location: { kind: "values", param: "location_in" },
  status: { kind: "values" },
  tier: { kind: "values" },
  category: { kind: "values" },
  safety: { kind: "values" },
  ats: { kind: "values" },
  qa_passed: { kind: "values" },
  fit: { kind: "range" },
  qa_score: { kind: "range" },
  found_at: { kind: "date" },
  applied_at: { kind: "date" },
  closes_at: { kind: "date" },
} as const satisfies Record<string, { kind: "values" | "range" | "date"; param?: string }>;
export type FilterField = keyof typeof FILTERS;
export type ColumnFilter = { kind: "values"; values: string[] } | { kind: "range"; min: string; max: string };
export type Filters = Partial<Record<FilterField, ColumnFilter>>;

export interface JobsView {
  tab: TabKey;
  q: string;
  location: string;
  sort: string;
  hidden: string[];
  selected: string[];
  filters: Filters;
}

export function isFilterField(f: string): f is FilterField {
  return Object.hasOwn(FILTERS, f);
}

function readFilter(field: FilterField, raw: string): ColumnFilter | null {
  if (FILTERS[field].kind === "values") {
    const values = raw.split(",").filter(Boolean).map(decodeURIComponent);
    return values.length ? { kind: "values", values } : null;
  }
  const at = raw.indexOf("..");
  if (at < 0) return null;
  const [min, max] = [raw.slice(0, at).trim(), raw.slice(at + 2).trim()];
  return min || max ? { kind: "range", min, max } : null;
}

function writeFilter(f: ColumnFilter): string {
  return f.kind === "values" ? f.values.map(encodeURIComponent).join(",") : `${f.min}..${f.max}`;
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
    location: p.get("loc") ?? "",
    sort: validSort(p.get("sort")),
    hidden: list(p.get("cols")).filter((c) => (HIDEABLE as readonly string[]).includes(c)),
    selected: list(p.get("sel")),
    filters: readFilters(p),
  };
}

function readFilters(p: URLSearchParams): Filters {
  const out: Filters = {};
  for (const [k, v] of p) {
    if (!k.startsWith("f.")) continue;
    const field = k.slice(2);
    if (!isFilterField(field)) continue;
    const f = readFilter(field, v);
    if (f) out[field] = f;
  }
  return out;
}

export function writeView(p: URLSearchParams, patch: Partial<JobsView>): URLSearchParams {
  const next = new URLSearchParams(p);
  const set = (k: string, v: string, dflt = "") => (v && v !== dflt ? next.set(k, v) : next.delete(k));
  if (patch.tab !== undefined) set("tab", patch.tab, DEFAULT_TAB);
  if (patch.q !== undefined) set("q", patch.q.trim());
  if (patch.location !== undefined) set("loc", patch.location.trim());
  if (patch.sort !== undefined) set("sort", patch.sort, DEFAULT_SORT);
  if (patch.hidden !== undefined) set("cols", patch.hidden.join(","));
  if (patch.selected !== undefined) set("sel", patch.selected.join(","));
  if (patch.filters !== undefined) {
    for (const k of [...next.keys()]) if (k.startsWith("f.")) next.delete(k);
    for (const [field, f] of Object.entries(patch.filters)) if (f) next.set(`f.${field}`, writeFilter(f));
  }
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
  location: "location",
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
