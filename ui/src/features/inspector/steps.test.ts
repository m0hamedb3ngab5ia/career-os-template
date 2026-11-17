import { describe, expect, it } from "vitest";
import { currentStep, deriveSteps, withoutFrontmatter } from "./steps";

const states = (i: Parameters<typeof deriveSteps>[0]) => deriveSteps(i).map((s) => s.state);

describe("deriveSteps", () => {
  it("only scored: drafting is next", () => {
    expect(states({ status: "scored", fit: 80, files: [] })).toEqual(["done", "current", "todo", "todo", "todo"]);
  });
  it("drafted, no check yet", () => {
    expect(states({ status: "prepared", fit: 80, files: ["resume.pdf", "cover_letter.md"] })).toEqual(["done", "done", "current", "todo", "todo"]);
  });
  it("failed quality check stops there", () => {
    const s = deriveSteps({ status: "needs_review", fit: 70, files: ["resume.txt", "cover_letter.txt"], qaPassed: false });
    expect(s.map((x) => x.state)).toEqual(["done", "done", "failed", "todo", "todo"]);
    expect(currentStep(s)).toBe("Quality check");
  });
  it("queued is ready to apply", () => {
    expect(states({ status: "queued", fit: 90, files: ["resume.pdf", "cover_letter.pdf"], qaPassed: true })).toEqual(["done", "done", "done", "done", "current"]);
  });
  it("applied finishes everything", () => {
    expect(states({ status: "interview", fit: 90, files: [] })).toEqual(["done", "done", "done", "done", "done"]);
  });
});

describe("withoutFrontmatter", () => {
  it("drops a leading YAML block and keeps the letter", () => {
    expect(withoutFrontmatter("---\njob_id: x\nvoice_verified: false\n---\n\nDear team,\nHi.")).toBe("Dear team,\nHi.");
    expect(withoutFrontmatter("Dear team,\n---\nnot frontmatter")).toBe("Dear team,\n---\nnot frontmatter");
  });
});
