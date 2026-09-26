// All dates, times and numbers go through Intl (docs/UI.md build checklist). Locale: the browser's.

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
const nf = new Intl.NumberFormat();

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
  ["second", 1],
];

export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const diff = Math.round((t - now.getTime()) / 1000);
  const abs = Math.abs(diff);
  for (const [unit, secs] of UNITS) {
    if (abs >= secs || unit === "second") return rtf.format(Math.round(diff / secs), unit);
  }
  return null;
}

export function formatCount(n: number): string {
  return nf.format(n);
}
