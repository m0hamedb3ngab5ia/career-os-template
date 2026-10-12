import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { NeedsYou } from "./NeedsYou";
import { defaultRoutes, json, mockApi, NOW, renderWithApp, today, type Routes } from "./testing";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function setup(path = "/", routes: Routes = {}) {
  const calls = mockApi({ ...defaultRoutes(), ...routes });
  const r = renderWithApp(<NeedsYou />, { path });
  return { ...r, calls };
}
const rowTitles = () => screen.getAllByRole("listitem").map((li) => li.querySelector("[class*=rowTitle]")?.textContent).filter(Boolean);

const G = "Interview invite: pick a slot";

describe("NeedsYou", () => {
  it("shows ordered rows: one-sentence title with the company, no category line, one short CTA; no priority labels", async () => {
    setup();
    await screen.findByText(G);
    expect(screen.getByRole("heading", { name: /^Needs your attention/ })).toBeInTheDocument();
    expect(rowTitles()[1]).toBe(G);
    expect(rowTitles()).toContain("Review Acme Robotics application");
    expect(screen.queryByText(/APPLICATION ·|PROFILE|Needs a decision from you/)).not.toBeInTheDocument();
    const acme = screen.getByText("Review Acme Robotics application").closest("li")!;
    expect(within(acme).getByText("Approval required before submission.")).toBeInTheDocument();
    expect(within(acme).getByRole("link", { name: "Review" })).toHaveAttribute("href", "/jobs/j-acme");
    expect(screen.queryByText(/^(High|Medium|Low)$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/master\.yaml/)).not.toBeInTheDocument();
  });

  it("offers Mark done only for tasks the system can't detect as finished", async () => {
    setup();
    await screen.findByText(G);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Mark done/ }).map((b) => b.getAttribute("aria-label"))).toEqual(["Mark done: Globex", "Mark done: Hooli"]);
  });

  it("has its own empty state when nothing is open", async () => {
    setup("/", { "GET /api/today": { actions: [], prepare_queue: { total: 0 } } });
    expect(await screen.findByRole("heading", { name: "Nothing needs you" })).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
  });

  it("mark done removes the row at once, posts done, and Undo posts reopen and brings it back", async () => {
    const user = userEvent.setup();
    let open = today.actions!;
    const { calls } = setup("/", {
      "GET /api/today": () => json({ ...today, actions: open }),
      "POST /api/actions/12/done": () => {
        open = open.filter((a) => a.id !== "12");
        return json({ ok: ["12"], queued: [], missing: [] });
      },
      "POST /api/actions/12/reopen": () => {
        open = today.actions!;
        return json({ ok: ["12"], queued: [], missing: [] });
      },
    });
    await screen.findByText(G);
    await user.click(screen.getByRole("button", { name: "Mark done: Globex" }));
    await waitFor(() => expect(screen.queryByText(G)).not.toBeInTheDocument());
    const toast = await screen.findByText("Marked Globex done.");
    expect(toast.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
    const done = calls.find((c) => c.method === "POST" && c.path === "/api/actions/12/done");
    expect(done?.headers.get("X-CareerOS")).toBe("1");

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText(G)).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/api/actions/12/reopen")).toBe(true),
    );
  });

  it("after mark done, focus moves to the next row's Mark done, else its CTA", async () => {
    const user = userEvent.setup();
    let open = today.actions!;
    setup("/", {
      "GET /api/today": () => json({ ...today, actions: open }),
      "POST /api/actions/12/done": () => {
        open = open.filter((a) => a.id !== "12");
        return json({ ok: ["12"], queued: [], missing: [] });
      },
    });
    await screen.findByText(G);
    await user.click(screen.getByRole("button", { name: "Mark done: Globex" }));
    await waitFor(() => expect(screen.queryByText(G)).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("link", { name: "Review" })).toHaveFocus());
  });

  it("after mark done on the last row, focus moves to the list heading", async () => {
    const user = userEvent.setup();
    let open = today.actions!.filter((a) => a.id === "12");
    setup("/", {
      "GET /api/today": () => json({ ...today, actions: open }),
      "POST /api/actions/12/done": () => {
        open = [];
        return json({ ok: ["12"], queued: [], missing: [] });
      },
    });
    await user.click(await screen.findByRole("button", { name: "Mark done: Globex" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /^Needs your attention/ })).toHaveFocus());
  });

  it("puts the row back and shows the server's reason when mark done fails", async () => {
    const user = userEvent.setup();
    setup("/", { "POST /api/actions/12/done": { $status: 409, body: { detail: "Tracker is busy" } } });
    await screen.findByText(G);
    await user.click(screen.getByRole("button", { name: "Mark done: Globex" }));
    expect(await screen.findByText(/Tracker is busy/)).toBeInTheDocument();
    expect(screen.getByText(G)).toBeInTheDocument();
  });

  it("says when the change is queued behind an open tracker", async () => {
    const user = userEvent.setup();
    setup("/", { "POST /api/actions/12/done": () => json({ ok: [], queued: ["12"], missing: [] }) });
    await screen.findByText(G);
    await user.click(screen.getByRole("button", { name: "Mark done: Globex" }));
    expect(await screen.findByText(/Marked Globex done\. .*queued/)).toBeInTheDocument();
  });

  it("shows an error with Retry when the list can't load", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/", { "GET /api/today": { $status: 503, body: { detail: "config/pipeline.yaml: bad" } } });
    expect(await screen.findByText(/config\/pipeline\.yaml: bad/)).toBeInTheDocument();
    const before = calls.filter((c) => c.path === "/api/today").length;
    await act(() => user.click(screen.getByRole("button", { name: "Retry" })));
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/today").length).toBeGreaterThan(before));
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await screen.findByText(G);
    expect(await axeViolations(container)).toEqual([]);
  });
});
