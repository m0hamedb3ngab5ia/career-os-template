// All dates, times and numbers go through Intl (docs/UI.md build checklist). Default locale: the browser's.

const rtfs = new Map<string, Intl.RelativeTimeFormat>();
const nfs = new Map<string, Intl.NumberFormat>();

function rtf(locale?: string): Intl.RelativeTimeFormat {
  const k = locale ?? "";
  let f = rtfs.get(k);
  if (!f) rtfs.set(k, (f = new Intl.RelativeTimeFormat(locale, { numeric: "auto" })));
  return f;
}

function nf(locale?: string): Intl.NumberFormat {
  const k = locale ?? "";
  let f = nfs.get(k);
  if (!f) nfs.set(k, (f = new Intl.NumberFormat(locale)));
  return f;
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
  ["second", 1],
];

export function formatRelative(iso: string | null | undefined, now: Date = new Date(), locale?: string): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const diff = Math.round((t - now.getTime()) / 1000);
  const abs = Math.abs(diff);
  for (const [unit, secs] of UNITS) {
    if (abs >= secs || unit === "second") return rtf(locale).format(Math.round(diff / secs), unit);
  }
  return null;
}

export function formatCount(n: number, locale?: string): string {
  return nf(locale).format(n);
}
