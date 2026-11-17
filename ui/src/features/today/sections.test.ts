import { describe, expect, it } from "vitest";
import { buildSections, summary } from "./sections";
import { actionItem } from "./testing";
import type { OutreachItem } from "./types";

const row = (over: Parameters<typeof actionItem>[0]) => buildSections([over && actionItem(over)])[0]!.rows[0]!;

describe("eligibility copy", () => {
  const base = { id: "1", job_id: "j1", company: "Globex", role: "Engineer", type: "review" };
  it("reads a month-name range and the graduation month", () => {
    const r = row({ ...base, what: "Posting requires graduation between Dec 2026 and Jun 2027; candidate graduated May 2026. Confirm eligibility before applying." });
    expect(r.why).toBe("Wants a Dec 2026–Jun 2027 graduate. You graduated May 2026.");
  });
  it("reads a dashed range and an ISO graduation month", () => {
    const r = row({ ...base, what: "Posting is for students graduating Dec 2026-Jun 2027; candidate graduated 2026-05" });
    expect(r.why).toBe("Wants a Dec 2026–Jun 2027 graduate. You graduated May 2026.");
  });
  it("puts eligibility ahead of generic review in its own section", () => {
    const secs = buildSections([actionItem({ ...base, what: "Candidate graduated May 2026; posting wants graduating Dec 2026. Confirm eligibility" })]);
    expect(secs.map((s) => s.title)).toEqual(["Check you’re eligible"]);
  });
});

describe("résumé copy", () => {
  it("turns QA numbers into plain words", () => {
    const r = row({ id: "2", job_id: "j2", company: "Initech", type: "qa_fail",
      what: "qa_failed: relevance=5 (keyword coverage 0.375; no Go, GCP or blockchain/stablecoin evidence; weak summary)" });
    expect(r.why).toBe("Covers 38% of the posting’s keywords. Your profile doesn’t show Go, GCP, blockchain or stablecoin.");
    expect(r.cta).toBe("Review");
    expect(r.detected).toBe(true);
  });
});

describe("follow up", () => {
  it("is its own section, in plain words, opening the job", () => {
    const secs = buildSections([actionItem({ id: "9", job_id: "j1", company: "Nimbus", role: "Engineer", type: "follow_up",
      what: "No reply in 11 days. Send a short follow-up." })]);
    expect(secs.map((s) => s.key)).toEqual(["followup"]);
    expect(secs[0]!.title).toBe("Follow up");
    const r = secs[0]!.rows[0]!;
    expect(r.why).toBe("No reply in 11 days. Send a short follow-up.");
    expect(r.href).toBe("?job=j1");
    expect(r.detected).toBe(false);
  });
});

describe("stale postings", () => {
  it("merges a company's ghost jobs into one row with an age", () => {
    const g = (id: string, job: string) => ({ id, job_id: job, company: "Umbrella Labs", type: "ghost_job",
      what: "Posting may be stale: 8 jobs at Umbrella Labs", detail: `posted ${id === "3" ? 813 : 120} days ago` });
    const secs = buildSections([actionItem(g("3", "a")), actionItem(g("4", "b"))]);
    expect(secs[0]!.rows).toHaveLength(1);
    expect(secs[0]!.rows[0]!.why).toBe("8 postings, oldest up for 2+ years.");
    expect(secs[0]!.rows[0]!.detected).toBe(false);
  });
  it("uses months for mid-age postings and a fallback with no age", () => {
    const a = (detail: string | null) => row({ id: "5", company: "Acme Robotics", type: "ghost_job", what: "Posting may be stale: 1 job at Acme Robotics", detail });
    expect(a("posted 90 days ago").why).toBe("1 posting, oldest up for 3 months.");
    expect(a(null).why).toBe("1 posting not updated in a while.");
  });
});

describe("safety copy", () => {
  it("names the scam and the hidden-text cases", () => {
    const base = { id: "6", job_id: "j6", company: "Hooli", what: "x" };
    expect(row({ ...base, type: "scam_suspected" })).toMatchObject({ why: "Asks applicants for money. Blocked.", cta: "Read posting" });
    expect(row({ ...base, id: "7", type: "injection_suspected" }).why).toBe("Has text hidden from readers. Read it before applying.");
  });
});

describe("rows", () => {
  it("collapses the same job twice into one row holding both items", () => {
    const mk = (id: string) => actionItem({ id, job_id: "j1", company: "Globex", type: "question", what: "Answer a question" });
    const secs = buildSections([mk("1"), mk("2")]);
    expect(secs[0]!.rows).toHaveLength(1);
    expect(secs[0]!.rows[0]!.items).toHaveLength(2);
  });
  it("names a job-less item from its text", () => {
    const r = row({ id: "8", company: "", type: "review", what: "Acme SWE New Grad (0a1b2c3d4e5f): review before sending" });
    expect(r.title).toBe("Acme SWE New Grad");
    expect(r.href).toBeNull();
  });
  it("skips done items and orders sections by what you do next", () => {
    const secs = buildSections([
      actionItem({ id: "1", company: "A", type: "ghost_job", what: "Posting may be stale: 1 job" }),
      actionItem({ id: "2", job_id: "j", company: "B", type: "review", what: "review" }),
      actionItem({ id: "3", job_id: "k", company: "C", type: "review", what: "review", done: true }),
    ]);
    expect(secs.map((s) => s.key)).toEqual(["send", "stale"]);
    expect(secs[0]!.rows).toHaveLength(1);
  });
});

describe("summary", () => {
  it("says all caught up when empty", () => {
    expect(summary(buildSections([]))).toBe("You’re all caught up.");
  });
  it("leads with the first section and counts the rest", () => {
    const secs = buildSections([
      actionItem({ id: "1", job_id: "a", company: "A", type: "review", what: "r" }),
      actionItem({ id: "2", job_id: "b", company: "B", type: "review", what: "r" }),
      actionItem({ id: "3", company: "C", type: "ghost_job", what: "Posting may be stale: 2 jobs" }),
    ]);
    expect(summary(secs)).toBe("2 applications are ready to send. One other thing needs a look.");
    expect(summary(secs.slice(0, 1))).toBe("2 applications are ready to send.");
  });
});

describe("where a row links", () => {
  const base = { id: "9", job_id: "j9", company: "Globex", role: "Engineer", link: "https://jobs.example.com/globex/9" };
  it("opens the inspector for any row with a job", () => {
    for (const type of ["review", "qa_fail", "other"]) {
      expect(row({ ...base, type, what: "Something" }).href).toBe("?job=j9");
    }
  });
  it("sends safety and stale rows to the posting in a new tab", () => {
    for (const type of ["scam_suspected", "injection_suspected", "ghost_job"]) {
      expect(row({ ...base, type, what: "x" })).toMatchObject({ href: base.link, external: true });
    }
  });
  it("has no link when the action has no posting URL", () => {
    expect(row({ ...base, link: "profile/master.yaml", type: "scam_suspected", what: "x" }).href).toBeNull();
  });
});

describe("Reach out", () => {
  const o = (over: Partial<OutreachItem> = {}): OutreachItem => ({
    job_id: "j1", company: "Acme Robotics", title: "Platform Engineer", contact_name: "Jane Doe", contact_role: "recruiter",
    email: "jane@acme.example", email_confidence: "medium", draft_ready: true, followup_due: null, ...over });
  const send = actionItem({ id: "1", job_id: "j9", company: "Globex", what: "review", type: "review" });

  it("sits right after Ready to send and links to the inspector", () => {
    const secs = buildSections([send], [o()]);
    expect(secs.map((s) => s.title)).toEqual(["Ready to send", "Reach out"]);
    const r = secs[1]!.rows[0]!;
    expect([r.title, r.sub, r.cta, r.href]).toEqual(["Acme Robotics", "Platform Engineer", "Open", "?job=j1"]);
    expect(r.why).toBe("Recruiter Jane Doe · email likely jane@acme.example · draft ready");
    expect(secs[1]!.caption).toBe("Drafts are written. You send them yourself.");
  });

  it("says unconfirmed for a low-confidence email and no draft when none", () => {
    expect(buildSections([], [o({ email_confidence: "low", draft_ready: false })])[0]!.rows[0]!.why)
      .toBe("Recruiter Jane Doe · email unconfirmed · no draft yet");
    expect(buildSections([], [o({ email_confidence: "verified", contact_role: "hiring_manager", followup_due: "2026-10-03" })])[0]!.rows[0]!.why)
      .toBe("Hiring manager Jane Doe · email jane@acme.example · draft ready · follow up by Oct 3");
  });

  it("leads the summary only when nothing comes before it", () => {
    expect(summary(buildSections([], [o()]))).toBe("One contact is ready to reach out to.");
    expect(summary(buildSections([send], [o()]))).toBe("One application is ready to send. One other thing needs a look.");
  });
});
