import { describe, expect, it } from "vitest";
import { dueInfo, formatDay, formatLongDate, formatPercent, formatWhen } from "./dates";

// Vitest pins TZ=UTC and en-US (vite.config.ts); the locale argument is passed where the test is about it.
const now = new Date("2026-09-25T10:00:00Z"); // a Friday
const en = "en-US";

describe("formatLongDate", () => {
  it("names the weekday and date", () => {
    expect(formatLongDate(now, en)).toBe("Friday, September 25");
    expect(formatLongDate(now, "fr-FR")).toBe("vendredi 25 septembre");
  });
});

describe("formatPercent", () => {
  it("rounds to a whole percent through Intl", () => {
    expect(formatPercent(7 / 41, en)).toBe("17%");
    expect(formatPercent(0.5, "fr-FR")).toMatch(/^50\s%$/);
  });
});

describe("formatWhen", () => {
  it("shows only the time today, relative words next to today, weekday within the week, then the date", () => {
    expect(formatWhen("2026-09-25T08:02:00Z", now, en)).toBe("8:02 AM");
    expect(formatWhen("2026-09-26T01:00:00Z", now, en)).toBe("Tomorrow, 1:00 AM");
    expect(formatWhen("2026-09-24T16:40:00Z", now, en)).toBe("Yesterday, 4:40 PM");
    expect(formatWhen("2026-09-21T16:40:00Z", now, en)).toBe("Mon 4:40 PM");
    expect(formatWhen("2026-10-09T03:00:00Z", now, en)).toBe("Oct 9, 3:00 AM");
  });

  it("returns null for missing or broken input", () => {
    expect(formatWhen(null, now, en)).toBeNull();
    expect(formatWhen("soon", now, en)).toBeNull();
  });
});

describe("formatDay", () => {
  it("uses Today, a weekday within the week, or a short date", () => {
    expect(formatDay("2026-09-25T01:00:00Z", now, en)).toBe("Today");
    expect(formatDay("2026-09-22T09:00:00Z", now, en)).toBe("Tue");
    expect(formatDay("2026-08-03T09:00:00Z", now, en)).toBe("Aug 3");
    expect(formatDay(undefined, now, en)).toBeNull();
  });
});

describe("dueInfo", () => {
  it("marks overdue items and says by how much", () => {
    expect(dueInfo("2026-09-24T09:00:00Z", now, en)).toEqual({ level: "overdue", text: "Overdue by 1 day" });
    expect(dueInfo("2026-09-25T07:00:00Z", now, en)).toEqual({ level: "overdue", text: "Overdue by 3 hours" });
  });

  it("uses relative words within 48 hours (soon)", () => {
    expect(dueInfo("2026-09-25T18:00:00Z", now, en)).toEqual({ level: "soon", text: "Today, 6:00 PM" });
    expect(dueInfo("2026-09-26T15:00:00Z", now, en)).toEqual({ level: "soon", text: "Tomorrow, 3:00 PM" });
  });

  it("says 'in N days' with the date within a week, then the absolute date (later)", () => {
    expect(dueInfo("2026-09-28T12:00:00Z", now, en)).toEqual({ level: "later", text: "In 3 days · Mon, Sep 28" });
    expect(dueInfo("2026-10-03T12:00:00Z", now, en)).toEqual({ level: "later", text: "Sat, Oct 3" });
  });

  it("has no due info without a date", () => {
    expect(dueInfo(null, now, en)).toBeNull();
    expect(dueInfo("", now, en)).toBeNull();
  });
});
