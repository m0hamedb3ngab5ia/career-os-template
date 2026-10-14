import { describe, expect, it } from "vitest";
import { reasonsLine } from "./reasons";

describe("reasonsLine (REQ-130)", () => {
  it("is Match pending without a match", () => {
    expect(reasonsLine(null)).toBe("Match pending");
    expect(reasonsLine(undefined)).toBe("Match pending");
  });
  it("shows covered/total and up to two missing skills", () => {
    expect(reasonsLine({ covered: 7, total: 10, missing: ["Go", "Kubernetes"] })).toBe("7/10 skills · missing: Go, Kubernetes");
  });
  it("collapses the rest to +n", () => {
    expect(reasonsLine({ covered: 5, total: 10, missing: ["Go", "Rust", "Kafka", "Redis"] })).toBe("5/10 skills · missing: Go, Rust, +2");
  });
  it("omits the missing part when nothing is missing", () => {
    expect(reasonsLine({ covered: 4, total: 4, missing: [] })).toBe("4/4 skills");
  });
});
