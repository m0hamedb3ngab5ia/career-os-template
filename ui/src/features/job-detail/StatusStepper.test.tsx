import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../../test/axe";
import { META } from "../jobs/fixtures";
import { buildSteps, StatusStepper } from "./StatusStepper";

const P = META.pipeline;

describe("buildSteps", () => {
  it("walks the Pipeline columns' statuses in order", () => {
    const steps = buildSteps("needs_review", [], P);
    expect(steps.map((s) => s.status)).toEqual(["found", "scored", "queued", "prepared", "needs_review", "applied",
      "screening", "interview", "offer"]);
    expect(steps.map((s) => s.state).join(",")).toBe("done,done,done,done,current,upcoming,upcoming,upcoming,upcoming");
  });

  it("a closed status is a terminal step after the furthest status reached", () => {
    const history = [
      { status: "found", at: "2026-09-01" },
      { status: "applied", at: "2026-09-10" },
      { status: "screening", at: "2026-09-12" },
      { status: "rejected", at: "2026-09-20" },
    ];
    const steps = buildSteps("rejected", history, P);
    expect(steps.map((s) => `${s.status}:${s.state}`)).toEqual([
      "found:done", "scored:done", "queued:done", "prepared:done", "needs_review:done", "applied:done",
      "screening:done", "rejected:current",
    ]);
    expect(steps.at(-1)!.terminal).toBe(true);
  });

  it("no status yet: everything upcoming", () => {
    expect(buildSteps(null, [], P).every((s) => s.state === "upcoming")).toBe(true);
  });
});

describe("StatusStepper", () => {
  it("is a labelled list with the current step marked and spoken state prefixes", async () => {
    const { container } = render(<StatusStepper steps={buildSteps("prepared", [], P)} />);
    const list = screen.getByRole("list", { name: "Application progress" });
    const current = within(list).getAllByRole("listitem").find((li) => li.getAttribute("aria-current") === "step")!;
    expect(current).toHaveTextContent("Current step: Prepared");
    const texts = within(list).getAllByRole("listitem").map((li) => li.textContent);
    expect(texts[0]).toBe("Done: Found");
    expect(texts.at(-1)).toBe("Upcoming: Offer");
    expect(await axeViolations(container)).toEqual([]);
  });
});
