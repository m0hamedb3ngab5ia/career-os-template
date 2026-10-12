import type { Doc } from "./api";
import { cap, type Entry, sectionOrder } from "./doc";

const s = (v: unknown) => (typeof v === "string" ? v.trim() : "");
const list = (v: unknown) => (Array.isArray(v) ? v.filter((x) => typeof x === "string" && x) as string[] : []);
const join = (xs: unknown[], sep: string) => xs.map(s).filter(Boolean).join(sep);

/**
 * Plain text as an ATS parser would read it: no suggestions, no layout. Follows the order of
 * templates/resume/resume_schema.md "Plain-text render order": header, summary, sections in order, entry heading,
 * subtitle, "- " bullets. Approximation of render.py's resume.txt built client-side from the draft (no endpoint).
 */
export function atsText(doc: Doc): string {
  const out: string[] = [];
  const id = (doc.identity as Record<string, unknown> | undefined) ?? {};
  out.push(s(id.name), join(Object.entries(id).filter(([k]) => k !== "name").map(([, v]) => v), " | "), "");
  if (s(doc.summary)) out.push("SUMMARY", s(doc.summary), "");
  for (const t of sectionOrder(doc)) {
    if (t === "skills") {
      out.push(s(doc.skills_heading).toUpperCase() || "SKILLS");
      const groups = (doc.skill_groups as { label?: string; items?: string[] }[] | undefined) ?? [];
      if (groups.length) for (const g of groups) { const it = list(g.items); if (it.length) out.push(`${s(g.label)}: ${it.join(", ")}`); }
      else for (const [k, v] of Object.entries((doc.skills as Record<string, string[]>) ?? {})) { const it = list(v); if (it.length) out.push(`${k}: ${it.join(", ")}`); }
      out.push("");
      continue;
    }
    out.push(t.toUpperCase());
    for (const e of (doc[t] as Entry[]) ?? []) {
      out.push(join([e.company, e.name, e.school, e.title, e.degree].filter((x) => x), " | ")
        || "", join([e.team, e.location, e.start && `${s(e.start)} – ${s(e.end)}`, e.date, e.gpa && `GPA ${s(e.gpa)}`], " | "));
      const stack = list(e.stack);
      if (stack.length) out.push(`Stack: ${stack.join(", ")}`);
      for (const l of (e.links as { label?: string; url?: string }[] | undefined) ?? []) out.push(`${s(l.label)}: ${s(l.url)}`);
      for (const k of ["coursework", "activities"]) { const it = list(e[k]); if (it.length) out.push(`${cap(k)}: ${it.join(", ")}`); }
      for (const b of e.bullets ?? []) out.push(`- ${b.text ?? ""}`);
    }
    out.push("");
  }
  return out.filter((l, i, a) => l || (i > 0 && a[i - 1])).join("\n").trim() + "\n";
}
