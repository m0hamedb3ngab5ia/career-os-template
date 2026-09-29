import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { NeedsYou } from "./NeedsYou";
import { actionItem, defaultRoutes, json, mockApi, NOW, renderWithApp, today, type Routes } from "./testing";

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
const rowNames = () =>
  screen
    .getAllByRole("listitem")
    .map((li) => li.querySelector("[data-company]")?.textContent)
    .filter(Boolean);

describe("NeedsYou", () => {
  it("lists every open item with company, role, what, due line, link, type, priority and needs", async () => {
    setup();
    const acme = (await screen.findByText("Acme Robotics")).closest("li")!;
    const row = within(acme);
    expect(row.getByText("Software Engineer, Platform")).toBeInTheDocument();
    expect(row.getByText(/Tier A: review/)).toBeInTheDocument();
    expect(row.getByText("Sat, Oct 3 · posting closes")).toHaveAttribute("data-level", "later");
    expect(row.getByRole("link", { name: /Open jobs\.example\.com/ })).toHaveAttribute("href", "https://jobs.example.com/acme/123");
    expect(row.getByRole("link", { name: /Open jobs\.example\.com/ })).toHaveAttribute("target", "_blank");
    expect(row.getByText("Review")).toBeInTheDocument();
    expect(row.getByText("High")).toBeInTheDocument();
    expect(row.getByText("Laptop")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Needs you 4" })).toBeInTheDocument();
  });

  it("colours the due line: red overdue, orange within 48 h, nothing when missing", async () => {
    setup();
    const hooli = within((await screen.findByText("Hooli")).closest("li")!);
    expect(hooli.getByText("Overdue by 1 day · note was due")).toHaveAttribute("data-level", "overdue");
    const globex = within(screen.getByText("Globex").closest("li")!);
    expect(globex.getByText("Tomorrow, 3:00 PM · reply within 48 hours")).toHaveAttribute("data-level", "soon");
    const initech = within(screen.getByText("Initech").closest("li")!);
    expect(initech.queryByText("No date")).not.toBeInTheDocument();
    expect(initech.queryByText("Anytime")).not.toBeInTheDocument();
  });

  it("shows plain task text and hides the empty 'Other' type", async () => {
    setup("/", {
      "GET /api/today": { ...today, actions: [actionItem({ id: 9, company: "Umbrella", job_id: "u1", what: "tier_a_review", type: "other" })] },
    });
    const row = within((await screen.findByText("Umbrella")).closest("li")!);
    expect(row.getByText("Review resume + cover letter")).toBeInTheDocument();
    expect(row.queryByText("Other")).not.toBeInTheDocument();
  });

  it("shows a non-web link as text, not an anchor; no link at all shows nothing", async () => {
    setup();
    const initech = within((await screen.findByText("Initech")).closest("li")!);
    expect(initech.getByText("profile/master.yaml").closest("a")).toBeNull();
    const hooli = within(screen.getByText("Hooli").closest("li")!);
    expect(hooli.queryByRole("link", { name: /^Open/ })).not.toBeInTheDocument();
  });

  it("groups tasks by job, blocked first, with one CTA per job to the job page", async () => {
    setup("/", {
      "GET /api/today": {
        ...today,
        actions: [
          ...today.actions!,
          actionItem({ id: "15", job_id: "j-acme", company: "Acme Robotics", role: "Software Engineer, Platform",
            what: "Answer 2 application questions", type: "question", priority: "M",
            detail: "careeros run: /apply-job stopped at question 4" }),
          actionItem({ id: "16", company: "", what: "Update your LinkedIn headline", priority: "L" }),
        ],
      },
    });
    const acme = within((await screen.findByText("Acme Robotics")).closest("li")!);
    expect(acme.getByText("2 things need attention")).toBeInTheDocument();
    expect(acme.getByRole("link", { name: "Answer questions" })).toHaveAttribute("href", "/jobs/j-acme");
    // The blocking question comes before the High-priority review; its raw detail sits behind Details.
    const tasks = acme.getAllByRole("checkbox").map((c) => c.getAttribute("aria-label"));
    expect(tasks[0]).toMatch(/Answer 2 application questions/);
    expect(acme.getByText("careeros run: /apply-job stopped at question 4").closest("details")).not.toBeNull();
    expect(rowNames()[0]).toBe("Acme Robotics");
    const other = within(screen.getByRole("heading", { name: "Other tasks" }).closest("li")!);
    expect(other.getByText("Update your LinkedIn headline")).toBeInTheDocument();
    expect(other.queryByRole("link", { name: /Continue|Review|Answer/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all tasks" })).toHaveAttribute("href", "/actions");
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
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
    await screen.findByText("Globex");
    await user.click(screen.getByRole("checkbox", { name: /^Mark Globex: Interview invite/ }));
    await waitFor(() => expect(screen.queryByText("Globex")).not.toBeInTheDocument());
    const toast = await screen.findByText("Marked Globex done.");
    expect(toast.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
    const done = calls.find((c) => c.method === "POST" && c.path === "/api/actions/12/done");
    expect(done?.headers.get("X-CareerOS")).toBe("1");

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText("Globex")).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/api/actions/12/reopen")).toBe(true),
    );
  });

  it("after mark done, focus moves to the next row's mark-done control", async () => {
    const user = userEvent.setup();
    let open = today.actions!;
    setup("/", {
      "GET /api/today": () => json({ ...today, actions: open }),
      "POST /api/actions/12/done": () => {
        open = open.filter((a) => a.id !== "12");
        return json({ ok: ["12"], queued: [], missing: [] });
      },
    });
    await screen.findByText("Globex");
    const names = rowNames();
    const i = names.indexOf("Globex");
    const next = names[i + 1] ?? names[i - 1];
    await user.click(screen.getByRole("checkbox", { name: /^Mark Globex: / }));
    await waitFor(() => expect(screen.queryByText("Globex")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("checkbox", { name: new RegExp(`^Mark ${next}: `) })).toHaveFocus());
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
    await user.click(await screen.findByRole("checkbox", { name: /^Mark Globex: / }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /^Needs you/ })).toHaveFocus());
  });

  it("puts the row back and shows the server's reason when mark done fails", async () => {
    const user = userEvent.setup();
    setup("/", { "POST /api/actions/12/done": { $status: 409, body: { detail: "Tracker is busy" } } });
    await screen.findByText("Globex");
    await user.click(screen.getByRole("checkbox", { name: /^Mark Globex: Interview invite/ }));
    expect(await screen.findByText(/Tracker is busy/)).toBeInTheDocument();
    expect(screen.getByText("Globex")).toBeInTheDocument();
  });

  it("says when the change is queued behind an open tracker", async () => {
    const user = userEvent.setup();
    setup("/", { "POST /api/actions/12/done": () => json({ ok: [], queued: ["12"], missing: [] }) });
    await screen.findByText("Globex");
    await user.click(screen.getByRole("checkbox", { name: /^Mark Globex: Interview invite/ }));
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
    await screen.findByText("Globex");
    expect(await axeViolations(container)).toEqual([]);
  });
});
