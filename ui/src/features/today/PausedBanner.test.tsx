import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PausedBanner } from "./PausedBanner";
import { defaultRoutes, mockApi, NOW, renderWithApp } from "./testing";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("PausedBanner", () => {
  it("says until when and resumes", async () => {
    const user = userEvent.setup();
    const calls = mockApi({ ...defaultRoutes(), "POST /api/runs/resume": { resumed: true } });
    renderWithApp(<PausedBanner paused={{ until: "2026-09-25T14:00:00Z", reason: "" }} now={NOW} />);
    expect(screen.getByText("Runs paused until 2:00 PM")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Resume" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/runs/resume")).toBe(true));
  });

  it("without an end time says until you resume", () => {
    mockApi(defaultRoutes());
    renderWithApp(<PausedBanner paused={{ until: null }} now={NOW} />);
    expect(screen.getByText("Runs paused until you resume")).toBeInTheDocument();
  });
});
