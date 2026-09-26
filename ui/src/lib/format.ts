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

type When = string | number | null | undefined;

/** ISO strings, or epoch seconds (file mtimes from the API). */
function toTime(v: When): number | null {
  if (v === null || v === undefined || v === "") return null;
  const t = typeof v === "number" ? v * 1000 : Date.parse(v);
  return Number.isNaN(t) ? null : t;
}

const dtfs = new Map<string, Intl.DateTimeFormat>();
function dtf(kind: "date" | "datetime", locale?: string): Intl.DateTimeFormat {
  const k = `${kind}|${locale ?? ""}`;
  let f = dtfs.get(k);
  if (!f) {
    const opts: Intl.DateTimeFormatOptions =
      kind === "date"
        ? { month: "short", day: "numeric" }
        : { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" };
    dtfs.set(k, (f = new Intl.DateTimeFormat(locale, opts)));
  }
  return f;
}

/** "Sep 23" (locale order and month names). */
export function formatDate(v: When, locale?: string): string | null {
  const t = toTime(v);
  return t === null ? null : dtf("date", locale).format(t);
}

/** "Sep 24, 6:02 PM". */
export function formatDateTime(v: When, locale?: string): string | null {
  const t = toTime(v);
  return t === null ? null : dtf("datetime", locale).format(t);
}

export function formatDecimal(n: number, digits = 1, locale?: string): string {
  return new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
}

/** File sizes: "512 byte", "48 kB", "1.8 MB". */
export function formatBytes(n: number, locale?: string): string {
  const [value, unit] =
    n >= 1e6 ? [n / 1e6, "megabyte"] : n >= 1e3 ? [n / 1e3, "kilobyte"] : [n, "byte"];
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit,
    unitDisplay: "short",
    maximumFractionDigits: value < 10 && unit !== "byte" ? 1 : 0,
  }).format(value);
}
