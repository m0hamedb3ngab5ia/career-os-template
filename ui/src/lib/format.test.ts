import { describe, expect, it } from "vitest";
import { formatCount, formatRelative } from "./format";

describe("format", () => {
  const now = new Date("2026-09-26T12:00:00Z");

  it("formats relative times with Intl, picking a sensible unit", () => {
    expect(formatRelative("2026-09-26T11:59:48Z", now)).toBe("12 seconds ago");
    expect(formatRelative("2026-09-26T11:58:00Z", now)).toBe("2 minutes ago");
    expect(formatRelative("2026-09-26T09:00:00Z", now)).toBe("3 hours ago");
    expect(formatRelative("2026-09-24T12:00:00Z", now)).toBe("2 days ago");
    expect(formatRelative("2026-09-26T12:00:00Z", now)).toBe("now");
  });

  it("returns null for missing or unparseable input", () => {
    expect(formatRelative(null, now)).toBeNull();
    expect(formatRelative("not a date", now)).toBeNull();
  });

  it("formats counts with grouping", () => {
    expect(formatCount(1736)).toBe("1,736");
  });
});
