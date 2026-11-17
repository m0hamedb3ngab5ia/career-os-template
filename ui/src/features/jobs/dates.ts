import { formatMonthDay } from "../../lib/format";

const DAY = 86_400_000;

/** "today", "yesterday", "3 days ago" for a YYYY-MM-DD / ISO date; null when unknown. */
export function daysAgo(iso: string | null | undefined, now: Date = new Date()): string | null {
  if (!iso) return null;
  const t = Date.parse(iso.length === 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(t)) return null;
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const n = Math.max(0, Math.round((start - new Date(new Date(t).getFullYear(), new Date(t).getMonth(), new Date(t).getDate()).getTime()) / DAY));
  return n === 0 ? "today" : n === 1 ? "yesterday" : `${n} days ago`;
}

/** "Posted 3 days ago · found Nov 12"; an unknown posted date leaves just "Found Nov 12". */
export function datesLine(job: { posted_at?: string | null; found_at?: string | null }, now?: Date): string | null {
  const posted = daysAgo(job.posted_at, now);
  const found = formatMonthDay(job.found_at);
  if (posted && found) return `Posted ${posted} · found ${found}`;
  if (posted) return `Posted ${posted}`;
  return found ? `Found ${found}` : null;
}
