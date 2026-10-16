import type { Doc } from "./api";

export const ENTRY_SECTIONS = ["experience", "projects", "leadership", "education"];
export const SKIP = new Set(["id", "source", "origin"]);
export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
export type Entry = Record<string, unknown> & { id?: string; bullets?: { id?: string; text?: string }[] };

/** Copy of `doc` with the value at `path` replaced. */
export function setAt(doc: Doc, path: (string | number)[], value: unknown): Doc {
  const out = structuredClone(doc);
  let node = out as Record<string | number, unknown>;
  for (const k of path.slice(0, -1)) node = node[k] as Record<string | number, unknown>;
  node[path[path.length - 1]!] = value;
  return out;
}

/** Section types in the résumé's own order (`sections[].order`), entry sections and skills only. */
export function sectionOrder(doc: Doc): string[] {
  const secs = ((doc.sections as { type: string; order?: number }[] | undefined) ?? []).slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const types = secs.map((s) => s.type);
  const has = (t: string) => Boolean(doc[t] || (t === "skills" && doc.skill_groups));
  for (const t of [...ENTRY_SECTIONS, "skills"]) if (has(t) && !types.includes(t)) types.push(t);
  return types.filter((t) => [...ENTRY_SECTIONS, "skills"].includes(t) && has(t));
}

/** Annotation targets with their text, in document order: summary, then every bullet. Cards follow this order. */
export function targetTexts(doc: Doc): [string, string][] {
  const out: [string, string][] = [["summary", String(doc.summary ?? "")]];
  for (const t of sectionOrder(doc)) for (const e of (ENTRY_SECTIONS.includes(t) ? (doc[t] as Entry[]) : [])) for (const b of e.bullets ?? []) if (b.id) out.push([b.id, b.text ?? ""]);
  return out;
}
export const targetOrder = (doc: Doc): string[] => targetTexts(doc).map(([id]) => id);

/** Text for case/whitespace-insensitive matching ("" for none). */
export const norm = (s: unknown): string => (typeof s === "string" ? s.toLowerCase().replace(/\s+/g, " ").trim() : "");

