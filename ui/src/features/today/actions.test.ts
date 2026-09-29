import { describe, expect, it } from "vitest";
import { groupByJob, jobCta, linkInfo } from "./actions";
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

describe("jobCta", () => {
  it("names the one next step from the job's tasks", () => {
    const cta = (...types: string[]) => jobCta(types.map((type, i) => actionItem({ id: String(i), company: "A", what: "x", type })));
    expect(cta("send_email", "question")).toBe("Answer questions");
    expect(cta("salary")).toBe("Answer questions");
    expect(cta("qa_fail")).toBe("Review documents");
    expect(cta("review")).toBe("Review documents");
    expect(cta("captcha")).toBe("Continue application");
  });
});

describe("linkInfo", () => {
  it("labels web links by host", () => {
    expect(linkInfo("https://www.example.com/jobs/123")).toEqual({ kind: "web", href: "https://www.example.com/jobs/123", label: "Open example.com" });
    expect(linkInfo("http://jobs.example.org")).toEqual({ kind: "web", href: "http://jobs.example.org", label: "Open jobs.example.org" });
  });
  it("shows anything that isn't http(s) as text, never as a broken anchor", () => {
    expect(linkInfo("profile/master.yaml")).toEqual({ kind: "text", text: "profile/master.yaml" });
    expect(linkInfo("javascript:alert(1)")).toEqual({ kind: "text", text: "javascript:alert(1)" });
  });
  it("has nothing for an empty link", () => {
    expect(linkInfo("")).toBeNull();
    expect(linkInfo(null)).toBeNull();
  });
});
