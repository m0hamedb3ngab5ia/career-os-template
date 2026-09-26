import { SOON_MS, parseTime } from "../../lib/dates";
import type { ActionItem } from "./types";

// Sorting, filtering and link handling for the "Needs you" list. Pure, so the screen and the tests share them.

export const SORTS = [
  { value: "priority", label: "Priority" },
  { value: "due", label: "Due date" },
  { value: "az", label: "A–Z" },
  { value: "newest", label: "Newest" },
] as const;
export type SortKey = (typeof SORTS)[number]["value"];

export const FILTERS = [
  { value: "all", label: "All" },
  { value: "overdue", label: "Overdue" },
  { value: "soon", label: "Due in 48 h" },
  { value: "high", label: "High priority" },
  { value: "phone", label: "Phone OK" },
  { value: "laptop", label: "Needs laptop" },
  { value: "nodate", label: "No date" },
] as const;
export type FilterKey = (typeof FILTERS)[number]["value"];

export const DEFAULT_SORT: SortKey = "priority";
export const DEFAULT_FILTER: FilterKey = "all";

export function parseSort(v: string | null): SortKey {
  return SORTS.some((s) => s.value === v) ? (v as SortKey) : DEFAULT_SORT;
}
export function parseFilter(v: string | null): FilterKey {
  return FILTERS.some((f) => f.value === v) ? (v as FilterKey) : DEFAULT_FILTER;
}

const PRIO: Record<string, number> = { H: 0, M: 1, L: 2 };
const prio = (a: ActionItem) => PRIO[a.priority ?? ""] ?? 3;
const due = (a: ActionItem) => parseTime(a.due)?.getTime() ?? Number.POSITIVE_INFINITY;
const created = (a: ActionItem) => parseTime(a.created)?.getTime() ?? Number.NEGATIVE_INFINITY;
const byDue = (a: ActionItem, b: ActionItem) => {
  const x = due(a);
  const y = due(b);
  return x === y ? 0 : x < y ? -1 : 1;
};

const SORTERS: Record<SortKey, (a: ActionItem, b: ActionItem) => number> = {
  priority: (a, b) => prio(a) - prio(b) || byDue(a, b),
  due: (a, b) => byDue(a, b) || prio(a) - prio(b),
  az: (a, b) => a.company.localeCompare(b.company) || prio(a) - prio(b),
  newest: (a, b) => created(b) - created(a) || prio(a) - prio(b),
};

export function sortActions(items: readonly ActionItem[], sort: SortKey): ActionItem[] {
  return items.toSorted(SORTERS[sort]);
}

export function filterActions(items: readonly ActionItem[], filter: FilterKey, now: Date): ActionItem[] {
  const t = now.getTime();
  const test: Record<FilterKey, (a: ActionItem) => boolean> = {
    all: () => true,
    overdue: (a) => due(a) < t,
    soon: (a) => due(a) - t <= SOON_MS,
    high: (a) => a.priority === "H",
    phone: (a) => a.needs === "phone" || a.needs === "anytime",
    laptop: (a) => a.needs === "laptop",
    nodate: (a) => parseTime(a.due) === null,
  };
  return items.filter(test[filter]);
}

export type LinkInfo = { kind: "web"; href: string; label: string } | { kind: "text"; text: string };

/** Web links open in a new tab, labelled by host; a path or any other scheme is shown as plain text. */
export function linkInfo(link: string | null | undefined): LinkInfo | null {
  const v = link?.trim();
  if (!v) return null;
  if (!/^https?:\/\//i.test(v)) return { kind: "text", text: v };
  let host = "";
  try {
    host = new URL(v).hostname.replace(/^www\./, "");
  } catch {
    return { kind: "text", text: v };
  }
  return { kind: "web", href: v, label: host ? `Open ${host}` : "Open link" };
}
