// All dates, times and numbers go through Intl (docs/UI.md build checklist). Default locale: the browser's,
// unless setAppLocale() picked one (tests pin en-US in src/test/setup.ts so output never depends on the machine).

let appLocale: string | undefined;

export function setAppLocale(locale: string | undefined): void {
  appLocale = locale;
}

export function getAppLocale(): string | undefined {
  return appLocale;
}

const rtfs = new Map<string, Intl.RelativeTimeFormat>();
const nfs = new Map<string, Intl.NumberFormat>();

function rtf(locale = appLocale): Intl.RelativeTimeFormat {
  const k = locale ?? "";
  let f = rtfs.get(k);
  if (!f) rtfs.set(k, (f = new Intl.RelativeTimeFormat(locale, { numeric: "auto" })));
  return f;
}

function nf(locale = appLocale): Intl.NumberFormat {
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
    const amount = new Intl.NumberFormat(locale ?? appLocale, { style: "unit", unit, unitDisplay: "long" }).format(n);
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

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** A wall-clock time ("01:00" from the schedule config) in the locale's style: "1:00 AM", "01:00". */
export function formatClock(hhmm: string, locale?: string): string {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm);
  if (!m) return hhmm;
  const d = new Date(2000, 0, 1, Number(m[1]), Number(m[2]));
  return dtf(locale, { hour: "numeric", minute: "2-digit" }).format(d);
}

/** When something happened or will happen: the time today, weekday + time within a week, else the date. */
export function formatWhen(iso: string | null | undefined, now: Date = new Date(), locale?: string): string | null {
  if (!iso) return null;
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return null;
  if (sameDay(t, now)) return dtf(locale, { hour: "numeric", minute: "2-digit" }).format(t);
  const days = Math.abs(t.getTime() - now.getTime()) / 86_400_000;
  if (days < 6) return dtf(locale, { weekday: "short", hour: "numeric", minute: "2-digit" }).format(t);
  return dtf(locale, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(t);
}

function unit(n: number, u: "hour" | "minute" | "second", locale?: string): string {
  const k = `${locale ?? ""}|u|${u}`;
  let f = nfs.get(k);
  if (!f) nfs.set(k, (f = new Intl.NumberFormat(locale, { style: "unit", unit: u, unitDisplay: "short" })));
  return f.format(n);
}

/** A duration in seconds: "42 sec", "7 min 12 sec", "2 hr 5 min". */
export function formatDuration(seconds: number | null | undefined, locale?: string): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return null;
  const s = Math.round(seconds);
  if (s < 60) return unit(s, "second", locale);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return m ? `${unit(h, "hour", locale)} ${unit(m, "minute", locale)}` : unit(h, "hour", locale);
  const rest = s % 60;
  return rest ? `${unit(m, "minute", locale)} ${unit(rest, "second", locale)}` : unit(m, "minute", locale);
}

/** A plain number in the locale ("12.5", "12,5"). */
export function formatNumber(n: number, locale?: string, maximumFractionDigits = 1): string {
  const k = `${locale ?? ""}|n|${maximumFractionDigits}`;
  let f = nfs.get(k);
  if (!f) nfs.set(k, (f = new Intl.NumberFormat(locale, { maximumFractionDigits })));
  return f.format(n);
}
