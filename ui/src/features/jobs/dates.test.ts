import { describe, expect, it } from "vitest";
import { datesLine } from "./dates";

const NOW = new Date(2026, 10, 15, 12);

describe("datesLine", () => {
  it("shows posted and found", () => {
    expect(datesLine({ posted_at: "2026-11-12", found_at: "2026-11-12T08:00:00" }, NOW)).toBe("Posted 3 days ago · found Nov 12");
  });
  it("unknown posted date leaves just found", () => {
    expect(datesLine({ posted_at: null, found_at: "2026-11-12T08:00:00" }, NOW)).toBe("Found Nov 12");
  });
  it("today and yesterday", () => {
    expect(datesLine({ posted_at: "2026-11-15", found_at: null }, NOW)).toBe("Posted today");
    expect(datesLine({ posted_at: "2026-11-14", found_at: null }, NOW)).toBe("Posted yesterday");
  });
});
