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

  it("colours the due line: red overdue, orange within 48 h, 'No date' when missing", async () => {
    setup();
    const hooli = within((await screen.findByText("Hooli")).closest("li")!);
    expect(hooli.getByText("Overdue by 1 day · note was due")).toHaveAttribute("data-level", "overdue");
    const globex = within(screen.getByText("Globex").closest("li")!);
    expect(globex.getByText("Tomorrow, 3:00 PM · reply within 48 hours")).toHaveAttribute("data-level", "soon");
    const initech = within(screen.getByText("Initech").closest("li")!);
    expect(initech.getByText("No date")).toHaveAttribute("data-level", "none");
  });

  it("shows a non-web link as text, not an anchor; no link at all shows nothing", async () => {
    setup();
    const initech = within((await screen.findByText("Initech")).closest("li")!);
    expect(initech.getByText("profile/master.yaml").closest("a")).toBeNull();
    const hooli = within(screen.getByText("Hooli").closest("li")!);
    expect(hooli.queryByRole("link")).not.toBeInTheDocument();
  });

  it("sorts by priority by default and keeps sort and filter in the URL", async () => {
    const user = userEvent.setup();
    const { router } = setup();
    await screen.findByText("Acme Robotics");
    expect(rowNames()).toEqual(["Globex", "Acme Robotics", "Hooli", "Initech"]);
    await user.click(screen.getByRole("radio", { name: "Due date" }));
    expect(router.state.location.search).toBe("?sort=due");
    expect(rowNames()).toEqual(["Hooli", "Globex", "Acme Robotics", "Initech"]);
    await user.click(screen.getByRole("radio", { name: "High priority" }));
    expect(new URLSearchParams(router.state.location.search).get("filter")).toBe("high");
    expect(rowNames()).toEqual(["Globex", "Acme Robotics"]);
    expect(screen.getByRole("heading", { name: "Needs you 2 of 4" })).toBeInTheDocument();
  });

  it("reads sort and filter from the URL", async () => {
    setup("/?sort=az&filter=phone");
    await screen.findByText("Globex");
    expect(screen.getByRole("radio", { name: "A–Z" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Phone OK" })).toHaveAttribute("aria-checked", "true");
    expect(rowNames()).toEqual(["Globex", "Hooli", "Initech"]);
  });

  it("arrow keys move through the sort control", async () => {
    const user = userEvent.setup();
    const { router } = setup();
    await screen.findByText("Globex");
    screen.getByRole("radio", { name: "Priority" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Due date" })).toHaveFocus();
    expect(router.state.location.search).toBe("?sort=due");
  });

  it("an empty filter result offers Clear filter", async () => {
    const user = userEvent.setup();
    const { router } = setup("/?filter=laptop", {
      "GET /api/today": { ...today, actions: today.actions!.filter((a) => a.needs !== "laptop") },
    });
    expect(await screen.findByText(/Nothing matches this filter/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear filter" }));
    expect(router.state.location.search).toBe("");
    expect(screen.getByText("Globex")).toBeInTheDocument();
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
      "POST /api/today/actions/12/done": () => {
        open = open.filter((a) => a.id !== 12);
        return json({ ok: true, queued: false });
      },
      "POST /api/today/actions/12/reopen": () => {
        open = today.actions!;
        return json({ ok: true, queued: false });
      },
    });
    await screen.findByText("Globex");
    await user.click(screen.getByRole("checkbox", { name: /^Mark Globex: Interview invite/ }));
    await waitFor(() => expect(screen.queryByText("Globex")).not.toBeInTheDocument());
    const toast = await screen.findByText("Marked Globex done.");
    expect(toast.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
    const done = calls.find((c) => c.method === "POST" && c.path === "/api/today/actions/12/done");
    expect(done?.headers.get("X-CareerOS")).toBe("1");

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText("Globex")).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/api/today/actions/12/reopen")).toBe(true),
    );
  });

  it("after mark done, focus moves to the next row's mark-done control", async () => {
    const user = userEvent.setup();
    let open = today.actions!;
    setup("/", {
      "GET /api/today": () => json({ ...today, actions: open }),
      "POST /api/today/actions/12/done": () => {
        open = open.filter((a) => a.id !== 12);
        return json({ ok: true, queued: false });
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
    let open = today.actions!.filter((a) => a.id === 12);
    setup("/", {
      "GET /api/today": () => json({ ...today, actions: open }),
      "POST /api/today/actions/12/done": () => {
        open = [];
        return json({ ok: true, queued: false });
      },
    });
    await user.click(await screen.findByRole("checkbox", { name: /^Mark Globex: / }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /^Needs you/ })).toHaveFocus());
  });

  it("puts the row back and shows the server's reason when mark done fails", async () => {
    const user = userEvent.setup();
    setup("/", { "POST /api/today/actions/12/done": { $status: 409, body: { detail: "Tracker is busy" } } });
    await screen.findByText("Globex");
    await user.click(screen.getByRole("checkbox", { name: /^Mark Globex: Interview invite/ }));
    expect(await screen.findByText(/Tracker is busy/)).toBeInTheDocument();
    expect(screen.getByText("Globex")).toBeInTheDocument();
  });

  it("says when the change is queued behind an open tracker", async () => {
    const user = userEvent.setup();
    setup("/", { "POST /api/today/actions/12/done": () => json({ ok: true, queued: true }) });
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
