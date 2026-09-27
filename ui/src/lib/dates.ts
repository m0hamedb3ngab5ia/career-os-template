// Dates, times and percentages for the screens, all through Intl (docs/UI.md build checklist). The locale defaults
// to the browser's; tests pass one explicitly where the wording is the point. Relative words ("Tomorrow") come from
// Intl.RelativeTimeFormat, so they follow the locale too.

const cache = new Map<string, Intl.DateTimeFormat | Intl.RelativeTimeFormat | Intl.NumberFormat>();

function memo<T extends Intl.DateTimeFormat | Intl.RelativeTimeFormat | Intl.NumberFormat>(key: string, make: () => T): T {
  let f = cache.get(key) as T | undefined;
  if (!f) cache.set(key, (f = make()));
  return f;
}

const dtf = (locale: string | undefined, opts: Intl.DateTimeFormatOptions) =>
  memo(`dt|${locale ?? ""}|${JSON.stringify(opts)}`, () => new Intl.DateTimeFormat(locale, opts));
const rtf = (locale: string | undefined) =>
  memo(`rt|${locale ?? ""}`, () => new Intl.RelativeTimeFormat(locale, { numeric: "auto" }));
const unitf = (locale: string | undefined, unit: string) =>
  memo(`u|${locale ?? ""}|${unit}`, () => new Intl.NumberFormat(locale, { style: "unit", unit, unitDisplay: "long" }));

const TIME: Intl.DateTimeFormatOptions = { hour: "numeric", minute: "2-digit" };
const WEEKDAY: Intl.DateTimeFormatOptions = { weekday: "short" };
const MONTH_DAY: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
const DAY_MS = 24 * 3600 * 1000;

export function parseTime(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : new Date(t);
}

function capitalize(s: string): string {
  return s ? s[0]!.toLocaleUpperCase() + s.slice(1) : s;
}

/** Whole local calendar days from `now` to `d` (tomorrow = 1, yesterday = -1). */
export function dayDiff(d: Date, now: Date): number {
  const a = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const b = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round((a - b) / DAY_MS);
}

function relDay(days: number, locale?: string): string {
  return capitalize(rtf(locale).format(days, "day"));
}

function shortDate(d: Date, now: Date, locale?: string): string {
  const opts = d.getFullYear() === now.getFullYear() ? MONTH_DAY : { ...MONTH_DAY, year: "numeric" as const };
  return dtf(locale, opts).format(d);
}

/** "Friday, September 25" */
export function formatLongDate(d: Date, locale?: string): string {
  return dtf(locale, { weekday: "long", month: "long", day: "numeric" }).format(d);
}

/** 0.17 → "17%" */
export function formatPercent(rate: number, locale?: string): string {
  return memo(`pc|${locale ?? ""}`, () => new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 0 })).format(
    rate,
  );
}

/** A point in time near now: "8:02 AM", "Tomorrow, 1:00 AM", "Mon 4:40 PM", "Oct 9, 3:00 AM". */
export function formatWhen(iso: string | null | undefined, now: Date = new Date(), locale?: string): string | null {
  const d = parseTime(iso);
  if (!d) return null;
  const days = dayDiff(d, now);
  const time = dtf(locale, TIME).format(d);
  if (days === 0) return time;
  if (Math.abs(days) === 1) return `${relDay(days, locale)}, ${time}`;
  if (Math.abs(days) < 7) return `${dtf(locale, WEEKDAY).format(d)} ${time}`;
  return `${shortDate(d, now, locale)}, ${time}`;
}

/** A day near now, no time: "Today", "Tue", "Aug 3". */
export function formatDay(iso: string | null | undefined, now: Date = new Date(), locale?: string): string | null {
  const d = parseTime(iso);
  if (!d) return null;
  const days = dayDiff(d, now);
  if (days === 0) return relDay(0, locale);
  if (Math.abs(days) < 7) return dtf(locale, WEEKDAY).format(d);
  return shortDate(d, now, locale);
}

export type DueLevel = "overdue" | "soon" | "later";
export interface DueInfo {
  level: DueLevel;
  text: string;
}

export const SOON_MS = 48 * 3600 * 1000;

/** Past due → "Overdue by 1 day"; within 48 h → "Today, 6:00 PM" / "Tomorrow, 3:00 PM"; within a week →
 * "In 3 days · Mon, Sep 28"; further out → "Sat, Oct 3". Red is for overdue only, orange for soon only. */
export function dueInfo(iso: string | null | undefined, now: Date = new Date(), locale?: string): DueInfo | null {
  const d = parseTime(iso);
  if (!d) return null;
  const ms = d.getTime() - now.getTime();
  const days = dayDiff(d, now);
  const dated = dtf(locale, { ...WEEKDAY, ...MONTH_DAY }).format(d);
  if (ms < 0) {
    const late = -ms;
    const [n, unit] =
      late >= DAY_MS
        ? [Math.floor(late / DAY_MS), "day"]
        : late >= 3600_000
          ? [Math.floor(late / 3600_000), "hour"]
          : [Math.max(1, Math.floor(late / 60_000)), "minute"];
    return { level: "overdue", text: `Overdue by ${unitf(locale, unit).format(n)}` };
  }
  const level: DueLevel = ms <= SOON_MS ? "soon" : "later";
  if (days <= 1) return { level, text: `${relDay(days, locale)}, ${dtf(locale, TIME).format(d)}` };
  if (days < 7) return { level, text: `${relDay(days, locale)} · ${dated}` };
  return { level, text: d.getFullYear() === now.getFullYear() ? dated : shortDate(d, now, locale) };
}
