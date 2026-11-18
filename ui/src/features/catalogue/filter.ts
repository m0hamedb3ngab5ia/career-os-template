import type { CatalogueSection } from "../../api/types";

/** Keep rows where every word of the query appears in any column; drop sections left empty. Flow order is kept. */
export function filterSections(sections: CatalogueSection[], query: string): CatalogueSection[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return sections;
  return sections
    .map((s) => ({
      ...s,
      rows: s.rows.filter((r) => {
        const hay = `${r.feature} ${r.what} ${r.how} ${r.req} ${s.title}`.toLowerCase();
        return words.every((w) => hay.includes(w));
      }),
    }))
    .filter((s) => s.rows.length);
}

/** Split "run `a b` or `c`" into text and code parts (backticks marked code). */
export function splitCode(text: string): { code: boolean; text: string }[] {
  return text
    .split(/(`[^`]+`)/)
    .filter(Boolean)
    .map((t) => (t.startsWith("`") && t.endsWith("`") && t.length > 1 ? { code: true, text: t.slice(1, -1) } : { code: false, text: t }));
}

/** A code span worth a Copy button: a careeros command or a /skill, not a file path. */
export function isCommand(text: string): boolean {
  return /^(\.venv\/bin\/)?careeros\s|^\/[a-z]/.test(text);
}
