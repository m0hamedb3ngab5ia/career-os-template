import { describe, expect, it } from "vitest";
import { formatCount, formatDay, formatDue, formatMonthDay, formatRelative } from "./format";

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
