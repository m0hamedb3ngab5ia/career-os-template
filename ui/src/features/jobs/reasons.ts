import type { JobListItem } from "./types";

/** REQ-130 reasons line: "<covered>/<total> skills · missing: <top 2>, +n"; no match yet → "Match pending". */
export function reasonsLine(r: JobListItem["reasons"]): string {
  if (!r) return "Match pending";
  const head = `${r.covered}/${r.total} skills`;
  if (!r.missing.length) return head;
  const rest = r.missing.length - 2;
  return `${head} · missing: ${r.missing.slice(0, 2).join(", ")}${rest > 0 ? `, +${rest}` : ""}`;
}
