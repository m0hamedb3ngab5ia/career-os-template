import { describe, expect, it } from "vitest";
import { changedSpan } from "./changedSpan";

describe("changedSpan", () => {
  it("splits the text into the shared start, the changed words and the shared end", () => {
    expect(changedSpan("an app on the App Store with a Chrome extension.", "an app in TestFlight beta with a Chrome extension."))
      .toEqual({ before: "an app ", del: "on the App Store", ins: "in TestFlight beta", after: " with a Chrome extension." });
  });
  it("whole text when nothing is shared; an insertion has an empty del", () => {
    expect(changedSpan("Worked on billing", "Fixed billing export bugs"))
      .toEqual({ before: "", del: "Worked on billing", ins: "Fixed billing export bugs", after: "" });
    expect(changedSpan("Built the service", "Built the billing service"))
      .toEqual({ before: "Built the ", del: "", ins: "billing ", after: "service" });
  });
});
