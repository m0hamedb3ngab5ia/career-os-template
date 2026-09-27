import { describe, expect, it } from "vitest";
import { formatBytes, formatClock, formatCount, formatDate, formatDateTime, formatDecimal, formatDay, formatDue, formatDuration, formatMonthDay, formatNumber, formatRelative, formatWhen, getAppLocale, setAppLocale } from "./format";

describe("format", () => {
  const now = new Date("2026-09-26T12:00:00Z");
  const en = "en-US";

  it("formats relative times with Intl, picking a sensible unit", () => {
    expect(formatRelative("2026-09-26T11:59:48Z", now, en)).toBe("12 seconds ago");
    expect(formatRelative("2026-09-26T11:58:00Z", now, en)).toBe("2 minutes ago");
    expect(formatRelative("2026-09-26T09:00:00Z", now, en)).toBe("3 hours ago");
    expect(formatRelative("2026-09-24T12:00:00Z", now, en)).toBe("2 days ago");
    expect(formatRelative("2026-09-26T12:00:00Z", now, en)).toBe("now");
  });

  it("follows the locale it is given", () => {
    expect(formatRelative("2026-09-26T11:58:00Z", now, "fr-FR")).toBe("il y a 2 minutes");
    expect(formatCount(1736, "de-DE")).toBe("1.736");
  });

  it("returns null for missing or unparseable input", () => {
    expect(formatRelative(null, now, en)).toBeNull();
    expect(formatRelative("not a date", now, en)).toBeNull();
  });

  it("formats counts with grouping", () => {
    expect(formatCount(1736, en)).toBe("1,736");
  });

  it("formats wall-clock schedule times in the locale's style", () => {
    expect(formatClock("01:00", en)).toBe("1:00 AM");
    expect(formatClock("18:30", "fr-FR")).toBe("18:30");
    expect(formatClock("nope", en)).toBe("nope");
  });

  it("formats a moment relative to today: time, weekday, or date", () => {
    const local = new Date(2026, 8, 26, 12, 0);
    const today = new Date(2026, 8, 26, 1, 5).toISOString();
    const thursday = new Date(2026, 8, 24, 20, 0).toISOString();
    const earlier = new Date(2026, 7, 2, 9, 0).toISOString();
    expect(formatWhen(today, local, en)).toBe("1:05 AM");
    expect(formatWhen(thursday, local, en)).toBe("Thu 8:00 PM");
    expect(formatWhen(earlier, local, en)).toBe("Aug 2, 9:00 AM");
    expect(formatWhen(null, local, en)).toBeNull();
  });

  it("formats durations and numbers with Intl units", () => {
    expect(formatDuration(42, en)).toBe("42 sec");
    expect(formatDuration(432, en)).toBe("7 min 12 sec");
    expect(formatDuration(7500, en)).toBe("2 hr 5 min");
    expect(formatDuration(null, en)).toBeNull();
    expect(formatNumber(12.5, "fr-FR")).toBe("12,5");
  });

  it("uses the app locale when no locale is passed (tests pin en-US in setup)", () => {
    expect(getAppLocale()).toBe("en-US");
    expect(formatRelative("2026-09-26T11:58:00Z", now)).toBe("2 minutes ago");
    setAppLocale("fr-FR");
    try {
      expect(formatRelative("2026-09-26T11:58:00Z", now)).toBe("il y a 2 minutes");
      expect(formatCount(1736)).toBe("1\u202f736");
    } finally {
      setAppLocale("en-US");
    }
  });
});

describe("formatDue", () => {
  const now = new Date("2026-09-24T15:00:00Z"); // Thursday; tests run in UTC
  const en = "en-US";

  it("words close deadlines relatively", () => {
    expect(formatDue("2026-09-24T18:00:00Z", false, now, en)).toBe("Today, 6:00 PM");
    expect(formatDue("2026-09-25T15:00:00Z", false, now, en)).toBe("Tomorrow, 3:00 PM");
    expect(formatDue("2026-09-25T23:59:59Z", true, now, en)).toBe("Tomorrow");
    expect(formatDue("2026-09-27T23:59:59Z", true, now, en)).toBe("In 3 days · Sun, Sep 27");
  });

  it("gives an absolute date further out", () => {
    expect(formatDue("2026-10-03T23:59:59Z", true, now, en)).toBe("Sat, Oct 3");
  });

  it("says how late an overdue item is", () => {
    expect(formatDue("2026-09-23T23:59:59Z", true, now, en)).toBe("Overdue by 1 day");
    expect(formatDue("2026-09-24T12:00:00Z", false, now, en)).toBe("Overdue by 3 hours");
  });

  it("follows the locale and handles missing input", () => {
    expect(formatDue("2026-09-25T15:00:00Z", false, now, "fr-FR")).toBe("Demain, 15:00");
    expect(formatDue(null, false, now, en)).toBeNull();
    expect(formatDay("bad", en)).toBeNull();
  });
});

describe("formatMonthDay", () => {
  it("gives month and day", () => {
    expect(formatMonthDay("2026-09-29T12:00:00Z", "en-US")).toBe("Sep 29");
    expect(formatMonthDay(null)).toBeNull();
  });
});

describe("dates, decimals and sizes", () => {
  const en = "en-US";

  it("formats a short date and a date with time in the given locale", () => {
    expect(formatDate("2026-09-23T12:00:00", en)).toBe("Sep 23");
    expect(formatDate("2026-09-23T12:00:00", "fr-FR")).toBe("23 sept.");
    expect(formatDateTime("2026-09-24T18:02:00", en)).toMatch(/^Sep 24, 6:02\sPM$/);
  });

  it("accepts epoch seconds (file mtimes) and returns null for nothing", () => {
    expect(formatDate(Date.parse("2026-09-23T12:00:00") / 1000, en)).toBe("Sep 23");
    expect(formatDate(null, en)).toBeNull();
    expect(formatDate("garbage", en)).toBeNull();
  });

  it("formats one-decimal scores and file sizes", () => {
    expect(formatDecimal(8.6, 1, en)).toBe("8.6");
    expect(formatDecimal(8.6, 1, "fr-FR")).toBe("8,6");
    expect(formatDecimal(8, 1, en)).toBe("8.0");
    expect(formatBytes(512, en)).toBe("512 bytes");
    expect(formatBytes(48_300, en)).toBe("48 kB");
    expect(formatBytes(1_800_000, en)).toBe("1.8 MB");
  });
});
