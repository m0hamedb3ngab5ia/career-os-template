import { describe, expect, it } from "vitest";
import { formatBytes, formatCount, formatDate, formatDateTime, formatDecimal, formatRelative } from "./format";

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
