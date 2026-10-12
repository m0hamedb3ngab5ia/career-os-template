import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { mockApi, renderRoutes } from "../../test/mockApi";
import { NextButton, NotCarriedOver, StatusBadge } from "./ImportPanels";

const imp = (restored = false) => ({ state: "done", dropped: [
  { id: "d1", text: "References available on request", restored },
  { id: "d2", text: "Hobbies: chess", restored: false },
] });

describe("StatusBadge", () => {
  it.each([["reviewing", "Reviewing"], ["draft", "Draft"], ["ready", "Ready"], ["failed", "Failed"]] as const)("%s", (s, label) => {
    renderRoutes([{ path: "/", element: <StatusBadge status={s} /> }], "/");
    expect(screen.getByText(label)).toBeInTheDocument();
  });
  it("renders nothing without a status", () => {
    const { container } = renderRoutes([{ path: "/", element: <StatusBadge /> }], "/");
    expect(container).toHaveTextContent("");
  });
});

describe("NotCarriedOver", () => {
  it("lists dropped lines, restores one, shows it as restored", async () => {
    let restored = false;
    const calls = mockApi({ "GET /api/profile/resumes/cv/import": () => imp(restored),
      "POST /api/profile/resumes/cv/import/dropped/d1/restore": () => { restored = true; return {}; } });
    const { container } = renderRoutes([{ path: "/", element: <NotCarriedOver rid="cv" /> }], "/");
    expect(await screen.findByText("References available on request")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Restore References available on request" }));
    expect(await screen.findByText("Restored")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/import/dropped/d1/restore"))).toBe(true);
    expect(screen.getAllByRole("button", { name: /^Restore / })).toHaveLength(1);
    expect(await axeViolations(container)).toEqual([]);
  });
  it("renders nothing when nothing was dropped", async () => {
    mockApi({ "GET /api/profile/resumes/cv/import": { state: "done", dropped: [] } });
    const { container } = renderRoutes([{ path: "/", element: <NotCarriedOver rid="cv" /> }], "/");
    await new Promise((r) => setTimeout(r, 20));
    expect(container).not.toHaveTextContent("Not carried over");
  });
});

describe("NextButton", () => {
  it("flushes, publishes as master, then calls onDone", async () => {
    const calls = mockApi({ "POST /api/profile/resumes/cv/publish": { n: 3 } });
    let done = 0;
    renderRoutes([{ path: "/", element: <NextButton rid="cv" flush={async () => true} onDone={() => { done++; }} /> }], "/");
    fireEvent.click(screen.getByRole("button", { name: /^Next/ }));
    await vi.waitFor(() => expect(done).toBe(1));
    expect(calls[0]?.body).toMatchObject({ master: true });
  });
});
