import { describe, expect, it } from "vitest";
import { changedSpan } from "./changedSpan";

describe("changedSpan", () => {
  it("keeps only the words that differ, with ellipses where text was cut", () => {
    expect(changedSpan("Lead iOS engineer of CTRL, an app on the App Store with a Chrome extension.",
      "Lead iOS engineer of CTRL, an app in TestFlight beta with a Chrome extension."))
      .toEqual({ before: "…", del: "on the App Store", ins: "in TestFlight beta", after: "…" });
  });
  it("whole text when nothing is shared; an insertion has an empty del", () => {
    expect(changedSpan("Worked on billing", "Fixed billing export bugs"))
      .toEqual({ before: "", del: "Worked on billing", ins: "Fixed billing export bugs", after: "" });
    expect(changedSpan("Built the service", "Built the billing service"))
      .toEqual({ before: "…", del: "", ins: "billing", after: "…" });
  });
});
