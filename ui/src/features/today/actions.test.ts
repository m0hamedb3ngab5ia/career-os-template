import { describe, expect, it } from "vitest";
import { groupByJob, taskRow } from "./actions";
import { actionItem } from "./testing";
import type { ActionItem } from "./types";

// Fictional companies only.
const items: ActionItem[] = [
  actionItem({ id: "1", company: "Globex", what: "a", priority: "L", needs: "anytime", created: "2026-09-20", due: null }),
  actionItem({ id: "2", company: "Acme Robotics", what: "b", priority: "H", needs: "laptop", created: "2026-09-24",
    due: "2026-10-03T12:00:00Z" }),
  actionItem({ id: "3", company: "Initech", what: "c", priority: "M", needs: "phone", created: "2026-09-22",
    due: "2026-09-24T09:00:00Z" }),
  actionItem({ id: "4", company: "Hooli", what: "d", priority: "H", needs: "phone", created: "2026-09-23",
    due: "2026-09-26T15:00:00Z" }),
];
const ids = (xs: ActionItem[]) => xs.map((x) => x.id);

describe("groupByJob", () => {
  const g = (over: Partial<ActionItem> & Pick<ActionItem, "id">) => actionItem({ company: "Acme Robotics", what: "x", ...over });
  const groups = groupByJob([
    g({ id: "1", job_id: "j-a", priority: "L", type: "review" }),
    g({ id: "2", job_id: null, company: "", priority: "H" }),
    g({ id: "3", job_id: "j-b", company: "Globex", priority: "H", type: "send_email", due: "2026-09-26T09:00:00Z" }),
    g({ id: "4", job_id: "j-a", priority: "M", type: "captcha" }),
    g({ id: "5", job_id: "j-b", company: "Globex", priority: "H", type: "send_email", due: "2026-09-25T12:00:00Z" }),
  ]);

  it("one group per job; tasks without a job are a final 'Other tasks' group", () => {
    expect(groups.map((x) => x.jobId)).toEqual(["j-a", "j-b", null]);
    expect(groups.map((x) => ids(x.items))).toEqual([["4", "1"], ["5", "3"], ["2"]]);
    expect(groups[1]).toMatchObject({ company: "Globex" });
  });

  it("orders blocked first, then priority, then due (groups by their top task)", () => {
    // j-a leads: its captcha blocks the application even though j-b has higher priority.
    expect(ids(groups[0]!.items)).toEqual(["4", "1"]);
    expect(ids(groups[1]!.items)).toEqual(["5", "3"]);
  });

  it("does not mutate its input", () => {
    const input = [...items];
    groupByJob(input);
    expect(ids(input)).toEqual(ids(items));
  });
});

describe("taskRow", () => {
  const row = (over: Partial<ActionItem>) => taskRow(actionItem({ id: "1", company: "Globex", what: "x", ...over }));
  it("has no category line; the company sits inside the title", () => {
    expect(row({ job_id: "j1", type: "review" })).not.toHaveProperty("category");
    expect(row({ job_id: "j1", type: "review" }).title).toBe("Review Globex application");
    expect(row({ job_id: "j1", type: "qa_fail" }).title).toBe("Review Globex résumé and cover letter");
  });
  it("placeholder-bullet action names the employer from the bullet id, no helper line", () => {
    expect(row({ job_id: "j1", type: "other", what: "Add real acme_ft bullets to your profile" })).toMatchObject({
      title: "Add Acme experience to your profile", why: "", cta: "Open", href: "/profile" });
  });
  it("maps known kinds to plain title, why and one CTA", () => {
    expect(row({ job_id: "j1", type: "review", what: "Tier A: review then submit" })).toMatchObject({
      title: "Review Globex application", why: "Approval required before submission.", cta: "Review", href: "/jobs/j1", detected: true });
    expect(row({ job_id: "j1", type: "qa_fail" })).toMatchObject({ title: "Review Globex résumé and cover letter", why: "", cta: "Review", detected: true });
    expect(row({ type: "other", company: "", what: "Connect the Claude-in-Chrome extension" })).toMatchObject({
      title: "Connect CareerOS to Chrome", why: "Required to continue browser-based applications.", cta: "Connect", href: "/settings" });
    expect(row({ company: "Initech", type: "profile_gap", what: "Bullet b3 is a placeholder" })).toMatchObject({
      title: "Add Initech experience to your profile", why: "", cta: "Open", href: "/profile" });
    expect(row({ job_id: "j1", type: "question" })).toMatchObject({ title: "Answer Globex application questions", cta: "Answer", detected: true });
  });
  it("falls back to plain task text, never file paths or commands; undetectable kinds can be marked done", () => {
    const r = row({ job_id: "j1", type: "send_email", what: "Run `careeros learn answer` and edit profile/master.yaml" });
    expect(r.detected).toBe(false);
    expect(`${r.title} ${r.why}`).not.toMatch(/master\.yaml|careeros /);
  });
});
