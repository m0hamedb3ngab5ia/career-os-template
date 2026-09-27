import { afterEach, describe, expect, it } from "vitest";
import { tomorrowAt, untilFor } from "./Banners";

const TZ = process.env.TZ;
afterEach(() => {
  process.env.TZ = TZ;
});

describe("Pause all › Until tomorrow", () => {
  it("is tomorrow at the configured local time", () => {
    const now = new Date(2026, 8, 26, 17, 40);
    const t = tomorrowAt(now, "08:00");
    expect([t.getFullYear(), t.getMonth(), t.getDate(), t.getHours(), t.getMinutes()]).toEqual([2026, 8, 27, 8, 0]);
    expect(untilFor("tomorrow", now, "06:30")).toBe(new Date(2026, 8, 27, 6, 30).toISOString());
    expect(untilFor("hour", now, "08:00")).toBe("+1h");
    expect(untilFor("resume", now, "08:00")).toBeNull();
  });

  it("stays on the wall clock across a DST change", () => {
    process.env.TZ = "America/New_York";
    const now = new Date(2026, 9, 31, 22, 0); // Sat 10 PM; clocks go back at 2 AM Sunday
    const t = tomorrowAt(now, "08:00");
    expect(t.getHours()).toBe(8);
    expect(t.toISOString()).toBe("2026-11-01T13:00:00.000Z"); // 8 AM EST: 11 hours later by the wall clock, 12 real hours
  });

  it("falls back to 08:00 on a malformed time", () => {
    expect(tomorrowAt(new Date(2026, 8, 26, 12, 0), "nope").getHours()).toBe(8);
  });
});
