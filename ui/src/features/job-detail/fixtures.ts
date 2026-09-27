import { job } from "../jobs/fixtures";
import type { JobDetail } from "./types";

// Fictional company and people only.
export function detail(over: Partial<JobDetail> = {}): JobDetail {
  return {
    job: job({ job_id: "nw01", company: "Northwind Labs", tier: "A", fit: 91, status: "needs_review" }),
    posting: {
      company: "Northwind Labs",
      title: "Software Engineer, Infrastructure",
      location: "Springfield",
      remote: false,
      url: "https://example.com/northwind/jobs/1",
      ats: "greenhouse",
    },
    status: "needs_review",
    history: [
      { status: "found", at: "2026-09-23T07:02:00" },
      { status: "scored", at: "2026-09-23T21:12:00" },
      { status: "needs_review", at: "2026-09-24T18:04:00", note: "prepare-job: Tier A" },
    ],
    score: {
      fit: 91,
      tier: "A",
      category: "swe",
      hard_filter_fails: [],
      reasons: ["Dream company"],
      matched_skills: ["Python", "Kubernetes"],
      missing_skills: ["Rust"],
    },
    safety: {
      verdict: "pass",
      flags: [
        {
          code: "GHOST_OLD_POST",
          level: "info",
          detail: "Posted 12 days ago",
          evidence: ["https://example.com/northwind/jobs/1", "ATS shows first published date"],
          at: "2026-09-23T07:02:00",
        },
        { code: "NEW_CODE_X", level: "review", detail: "Something new" },
      ],
      runs: 2,
    },
    qa: {
      rubric: { specificity: { score: 8.8, why: "Names the team" }, zero_fabrication: { score: 9.5 } },
      mean: 8.6,
      threshold: 7.5,
      pass: true,
      fail_reasons: [],
      next_action: "queue",
    },
    documents: [
      { name: "notes.txt", size: 120, modified: 1790000000 },
      { name: "resume.pdf", size: 48_300, modified: 1790000000 },
      { name: "cover_letter.md", size: 2_100, modified: 1790000000 },
    ],
    submitted: [],
    apply_session: {
      steps: [
        { time: "2026-09-24T18:02:00", action: "Opened form", ok: true },
        { time: "2026-09-24T18:03:00", action: "Uploaded resume.pdf", ok: true, note: "1 file" },
        { time: "2026-09-24T18:04:00", action: "Stopped before submit (Tier A)", ok: false },
      ],
      screenshots: ["screenshots/01_form.png", "screenshots/02_review.png"],
      outcome: "needs_review",
      reason: "Tier A is always you-submit",
      started: "2026-09-24T18:02:00",
      tier: "A",
      ats: "greenhouse",
    },
    screenshots: [
      { name: "01_form.png", size: 90_000, modified: 1790000000 },
      { name: "02_review.png", size: 91_000, modified: 1790000000 },
    ],
    contacts: [
      { name: "Jordan Lee", title: "Engineering Manager", mutuals: 4 },
      { name: "Riley Kim", title: "Technical Recruiter", linkedin_degree: 3, draft_message: "Hi Riley" },
    ],
    log: "",
    override: "",
    registry: { verified: null, flagged: null },
    outreach: { drafts: [{}, {}] },
    contacts_policy: [
      { name: "Jordan Lee", role: "Engineering Manager", manual: true, reason: "LINKEDIN_MUTUALS", detail: "4 mutual connections" },
      { name: "Riley Kim", role: "Technical Recruiter", manual: false, reason: null, detail: "" },
    ],
    activity: [
      { at: "2026-09-24T18:04:00", component: "prepare-job", message: "Status changed to Needs review" },
      { at: "2026-09-23T07:02:00", component: "scout", message: "Found by scout" },
    ],
    ...over,
  };
}
