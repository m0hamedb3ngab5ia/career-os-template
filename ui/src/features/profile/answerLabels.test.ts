import { describe, expect, it } from "vitest";
import { describeAnswer, groupAnswers } from "./answerLabels";

const a = (key: string, scope: "general" | "company" | "eeo" = "general", company: string | null = null) =>
  ({ key, scope, company, answer: "x", match: [], note: null });

describe("answerLabels", () => {
  it("maps known, eeo, company and unknown keys", () => {
    expect(describeAnswer(a("relocate"))).toEqual({ label: "Willing to relocate", group: "Job preferences" });
    expect(describeAnswer(a("gender", "eeo")).group).toBe("EEO (voluntary)");
    expect(describeAnswer(a("why_us", "company", "Acme"))).toEqual({ label: "Why us (Acme)", group: "Company-specific" });
    expect(describeAnswer(a("favorite_color"))).toEqual({ label: "Favorite color", group: "Other" });
  });
  it("groups in fixed order, dropping empty groups", () => {
    expect(groupAnswers([a("phone"), a("school"), a("degree")]).map((g) => [g.group, g.rows.length])).toEqual([["Education", 2], ["Personal information", 1]]);
  });
});
