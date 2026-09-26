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

const dtfs = new Map<string, Intl.DateTimeFormat>();
function dtf(locale: string | undefined, opts: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const k = `${locale ?? ""}|${JSON.stringify(opts)}`;
  let f = dtfs.get(k);
  if (!f) dtfs.set(k, (f = new Intl.DateTimeFormat(locale, opts)));
  return f;
}

function capitalize(s: string): string {
  return s ? s[0]!.toLocaleUpperCase() + s.slice(1) : s;
}

function dayNumber(d: Date): number {
  return Math.floor(new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() / 86_400_000);
}

/** "Fri, Oct 3" (weekday, month, day in the viewer's locale). */
export function formatDay(iso: string | null | undefined, locale?: string): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return dtf(locale, { weekday: "short", month: "short", day: "numeric" }).format(t);
}

/**
 * A deadline as the Action Items screen words it: relative when close ("Today, 6:00 PM", "Tomorrow",
 * "In 3 days · Sun, Sep 28", "Overdue by 1 day"), an absolute date further out ("Fri, Oct 3"). `dateOnly`
 * deadlines have no time of day.
 */
export function formatDue(
  iso: string | null | undefined,
  dateOnly: boolean,
  now: Date = new Date(),
  locale?: string,
): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const due = new Date(t);
  const time = dateOnly ? "" : dtf(locale, { hour: "numeric", minute: "2-digit" }).format(due);
  if (t < now.getTime()) {
    const hours = (now.getTime() - t) / 3_600_000;
    const [n, unit] = hours < 24 && !dateOnly ? [Math.max(1, Math.round(hours)), "hour"] : [Math.max(1, dayNumber(now) - dayNumber(due)), "day"];
    const amount = new Intl.NumberFormat(locale, { style: "unit", unit, unitDisplay: "long" }).format(n);
    return `Overdue by ${amount}`;
  }
  const days = dayNumber(due) - dayNumber(now);
  if (days <= 1) {
    const word = capitalize(rtf(locale).format(days, "day"));
    return time ? `${word}, ${time}` : word;
  }
  if (days <= 7) return `${capitalize(rtf(locale).format(days, "day"))} · ${formatDay(iso, locale)}`;
  return formatDay(iso, locale);
}

/** "Sep 29" (month and day in the viewer's locale). */
export function formatMonthDay(iso: string | null | undefined, locale?: string): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return dtf(locale, { month: "short", day: "numeric" }).format(t);
}
