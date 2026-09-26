import { describe, expect, it } from "vitest";
import {
  ACTION_TYPES,
  NEEDS,
  PRIORITIES,
  SAFETY,
  STATUSES,
  STOP_REASONS,
  describeCode,
  humanize,
} from "./labels";

// Codes copied from src/careeros/models.py and src/careeros/runs/runner.py. If the backend adds a code the
// UI still renders it (gray, humanized), but this list is the reminder to give it a proper label.
const MODEL_STATUSES = [
  "found", "scored", "skipped", "queued", "prepared", "needs_review", "applied",
  "screening", "interview", "offer", "rejected", "withdrawn", "ghosted",
];
const MODEL_ACTION_TYPES = [
  "captcha", "review", "question", "salary", "bot_detection", "qa_fail",
  "send_linkedin", "send_email", "profile_gap", "laptop_required", "scam_suspected", "ghost_job", "other",
];
const RUNNER_STOPS = [
  "completed", "budget_reached", "time_budget", "usage_limit", "auth_required", "permission_denied",
  "timeout", "consecutive_failures", "daily_cap", "paused", "cancelled", "doctor_failed", "error",
];

describe("label tables", () => {
  it("cover every code the backend defines", () => {
    expect(Object.keys(STATUSES).sort()).toEqual([...MODEL_STATUSES].sort());
    expect(Object.keys(ACTION_TYPES).sort()).toEqual([...MODEL_ACTION_TYPES].sort());
    for (const s of RUNNER_STOPS) expect(STOP_REASONS[s], s).toBeDefined();
    expect(Object.keys(SAFETY).sort()).toEqual(["block", "pass", "review", "skip"]);
    expect(Object.keys(PRIORITIES).sort()).toEqual(["H", "L", "M"]);
    expect(Object.keys(NEEDS).sort()).toEqual(["anytime", "laptop", "phone"]);
  });

  it("uses the mockup's plain-language, sentence-case labels", () => {
    expect(STATUSES.needs_review).toEqual({ label: "Needs review", tone: "orange" });
    expect(STATUSES.applied?.tone).toBe("teal");
    expect(ACTION_TYPES.scam_suspected?.label).toBe("Possible scam");
    expect(STOP_REASONS.auth_required).toMatchObject({ label: "Login needed", tone: "orange" });
    expect(STOP_REASONS.budget_reached?.label).toBe("Job budget used");
    for (const t of [STATUSES, ACTION_TYPES, STOP_REASONS]) {
      for (const { label } of Object.values(t)) expect(label[0]).toBe(label[0]!.toUpperCase());
    }
  });

  it("falls back to a gray, humanized label for unknown codes", () => {
    expect(describeCode(STATUSES, "on_hold")).toEqual({ label: "On hold", tone: "gray" });
    expect(describeCode(STATUSES, undefined)).toEqual({ label: "—", tone: "gray" });
    expect(humanize("QA_FAIL_hard")).toBe("Qa fail hard");
  });
});
