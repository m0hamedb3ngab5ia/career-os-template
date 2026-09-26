import { describe, expect, it } from "vitest";
import { formatCount, formatRelative } from "./format";

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
