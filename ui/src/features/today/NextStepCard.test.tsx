import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JustReadyNextStep, NextStepCard } from "./NextStepCard";
import { TodayPage } from "./TodayPage";
import { defaultRoutes, mockApi, renderWithApp } from "./testing";

afterEach(() => vi.unstubAllGlobals());

const step = (key: string, label: string, href: string | null) => ({ "GET /api/next-step": { key, label, href } });

describe("NextStepCard (REQ-122)", () => {
  it("E2E-014-02: readiness done and 0 ticked jobs -> Today card says Pick jobs and links to the Jobs list", async () => {
    mockApi({ ...defaultRoutes(), ...step("pick_jobs", "Pick jobs", "/jobs") });
    renderWithApp(<TodayPage />);
    expect(await screen.findByRole("heading", { name: "Next step" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Pick jobs" })).toHaveAttribute("href", "/jobs");
  });

  it("Find jobs starts a scout run", async () => {
    const calls = mockApi({ ...step("find_jobs", "Find jobs", null), "POST /api/runs/steps/scout": { run_id: "r1" },
      "GET /api/runs/r1": () => new Promise<Response>(() => {}) });
    renderWithApp(<NextStepCard />);
    await userEvent.click(await screen.findByRole("button", { name: "Find jobs" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/runs/steps/scout")).toBe(true));
    expect(await screen.findByRole("button", { name: /Finding jobs/ })).toBeDisabled();
  });

  it("is hidden when the API fails", async () => {
    const calls = mockApi({ "GET /api/next-step": { $status: 500, body: { detail: "x" } } });
    renderWithApp(<NextStepCard />);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(screen.queryByRole("heading", { name: "Next step" })).not.toBeInTheDocument();
  });

  it("Profile: shown once the last must-have closes, not when already ready", async () => {
    mockApi({ "GET /api/readiness": { ready: false, items: [] }, ...step("start_pipeline", "Start pipeline", "/pipeline/batch/new") });
    const { qc } = renderWithApp(<JustReadyNextStep />);
    await waitFor(() => expect(qc.getQueryData(["readiness"])).toBeTruthy());
    expect(screen.queryByRole("heading", { name: "Next step" })).not.toBeInTheDocument();
    act(() => qc.setQueryData(["readiness"], { ready: true, items: [] }));
    expect(await screen.findByRole("link", { name: "Start pipeline" })).toHaveAttribute("href", "/pipeline/batch/new");
  });

  it("Profile: no card when readiness is already done on load", async () => {
    const calls = mockApi({ "GET /api/readiness": { ready: true, items: [] }, ...step("pick_jobs", "Pick jobs", "/jobs") });
    const { qc } = renderWithApp(<JustReadyNextStep />);
    await waitFor(() => expect(qc.getQueryData(["readiness"])).toBeTruthy());
    expect(calls.some((c) => c.path === "/api/next-step")).toBe(false);
  });
});
