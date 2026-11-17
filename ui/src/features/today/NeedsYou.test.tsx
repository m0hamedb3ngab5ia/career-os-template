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
const G = "Interview invite: pick a slot.";
const titles = () => screen.getAllByRole("listitem").map((li) => li.querySelector("[class*=cellTitle]")?.textContent).filter(Boolean);

describe("NeedsYou", () => {
  it("groups rows into sections, each row a company, a reason and one link; no priority labels", async () => {
    setup();
    await screen.findByText(G);
    expect(screen.getByRole("heading", { level: 2, name: "Needs you, 4" })).toBeInTheDocument();
    const heads = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(heads).toEqual(["Ready to send 1", "Everything else 3"]);
    const acme = screen.getByText(/Acme Robotics/).closest("li")!;
    expect(within(acme).getByText(/Software Engineer, Platform/)).toBeInTheDocument();
    expect(within(acme).getByText("Check the résumé and cover letter, then send.")).toBeInTheDocument();
    expect(within(acme).getByRole("link", { name: "Review" })).toHaveAttribute("href", "/?job=j-acme");
    expect(screen.queryByText(/^(High|Medium|Low)$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/master\.yaml/)).not.toBeInTheDocument();
  });

  it("offers Dismiss only on rows the system can't detect as finished", async () => {
    setup();
    await screen.findByText(G);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Dismiss/ }).map((b) => b.getAttribute("aria-label")).sort()).toEqual(
      ["Dismiss: Globex", "Dismiss: Hooli", "Dismiss: Initech"]);
    const acme = screen.getByText(/Acme Robotics/).closest("li")!;
    expect(within(acme).queryByRole("button", { name: /Dismiss/ })).not.toBeInTheDocument();
  });

  it("shows 3 rows per section and a Show N more button for the rest", async () => {
    const user = userEvent.setup();
    const many = ["a", "b", "c", "d", "e"].map((k, i) =>
      actionItem({ id: `r${i}`, job_id: `j-${k}`, company: `Co ${k}`, what: "Posting looks thin", type: "other" }));
    setup("/", { "GET /api/today": { ...today, actions: many } });
    await screen.findByText("Co a");
    expect(titles()).toHaveLength(3);
    await user.click(screen.getByRole("button", { name: "Show 2 more" }));
    expect(titles()).toHaveLength(5);
    await user.click(screen.getByRole("button", { name: "Show less" }));
    expect(titles()).toHaveLength(3);
  });

  it("has its own empty state when nothing is open", async () => {
    setup("/", { "GET /api/today": { actions: [], prepare_queue: { total: 0 } } });
    expect(await screen.findByText(/^Nothing needs you\./)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Dismiss/ })).not.toBeInTheDocument();
  });

  it("Dismiss removes the row at once, posts done, and Undo posts reopen and brings it back", async () => {
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
    await user.click(screen.getByRole("button", { name: "Dismiss: Globex" }));
    await waitFor(() => expect(screen.queryByText(G)).not.toBeInTheDocument());
    const toast = await screen.findByText("Marked Globex done.");
    expect(toast.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
    const done = calls.find((c) => c.method === "POST" && c.path === "/api/actions/12/done");
    expect(done?.headers.get("X-CareerOS")).toBe("1");

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText(G)).toBeInTheDocument();
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/actions/12/reopen")).toBe(true));
  });

  it("after Dismiss, focus moves to the next row's Dismiss, else its link", async () => {
    const user = userEvent.setup();
    let open = today.actions!.filter((a) => a.id === "12" || a.id === "14");
    setup("/", {
      "GET /api/today": () => json({ ...today, actions: open }),
      "POST /api/actions/12/done": () => {
        open = open.filter((a) => a.id !== "12");
        return json({ ok: ["12"], queued: [], missing: [] });
      },
    });
    await screen.findByText(G);
    await user.click(screen.getByRole("button", { name: "Dismiss: Globex" }));
    await waitFor(() => expect(screen.queryByText(G)).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: "Dismiss: Hooli" })).toHaveFocus());
  });

  it("after Dismiss, focus moves to the next row on screen, not the next by priority", async () => {
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
    const rows = [...document.querySelectorAll<HTMLElement>("[data-action-id]")].map((e) => e.dataset.actionId);
    const after = rows[rows.indexOf("12") + 1] ?? rows[rows.indexOf("12") - 1];
    await user.click(screen.getByRole("button", { name: "Dismiss: Globex" }));
    await waitFor(() => expect(document.activeElement?.closest("[data-action-id]")?.getAttribute("data-action-id")).toBe(after));
  });

  it("falls back to the next row's link when that row has no Dismiss", async () => {
    const user = userEvent.setup();
    let open = today.actions!.filter((a) => a.id === "11" || a.id === "12");
    setup("/", {
      "GET /api/today": () => json({ ...today, actions: open }),
      "POST /api/actions/12/done": () => {
        open = open.filter((a) => a.id !== "12");
        return json({ ok: ["12"], queued: [], missing: [] });
      },
    });
    await user.click(await screen.findByRole("button", { name: "Dismiss: Globex" }));
    await waitFor(() => expect(screen.getByRole("link", { name: "Review" })).toHaveFocus());
  });

  it("after Dismiss on the last row, focus moves to the list heading", async () => {
    const user = userEvent.setup();
    let open = today.actions!.filter((a) => a.id === "12");
    setup("/", {
      "GET /api/today": () => json({ ...today, actions: open }),
      "POST /api/actions/12/done": () => {
        open = [];
        return json({ ok: ["12"], queued: [], missing: [] });
      },
    });
    await user.click(await screen.findByRole("button", { name: "Dismiss: Globex" }));
    await waitFor(() => expect(screen.getByRole("heading", { level: 2, name: /^Needs you/ })).toHaveFocus());
  });

  it("puts the row back and shows the server's reason when Dismiss fails", async () => {
    const user = userEvent.setup();
    setup("/", { "POST /api/actions/12/done": { $status: 409, body: { detail: "Tracker is busy" } } });
    await screen.findByText(G);
    await user.click(screen.getByRole("button", { name: "Dismiss: Globex" }));
    expect(await screen.findByText(/Tracker is busy/)).toBeInTheDocument();
    expect(screen.getByText(G)).toBeInTheDocument();
  });

  it("says when the change is queued behind an open tracker", async () => {
    const user = userEvent.setup();
    setup("/", { "POST /api/actions/12/done": () => json({ ok: [], queued: ["12"], missing: [] }) });
    await screen.findByText(G);
    await user.click(screen.getByRole("button", { name: "Dismiss: Globex" }));
    expect(await screen.findByText(/Marked Globex done\. .*queued/)).toBeInTheDocument();
  });

  it("shows an error with Try again when the list can't load", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/", { "GET /api/today": { $status: 503, body: { detail: "config/pipeline.yaml: bad" } } });
    expect(await screen.findByText(/config\/pipeline\.yaml: bad/)).toBeInTheDocument();
    const before = calls.filter((c) => c.path === "/api/today").length;
    await act(() => user.click(screen.getByRole("button", { name: "Try again" })));
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/today").length).toBeGreaterThan(before));
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await screen.findByText(G);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("shows a Reach out section after Ready to send; Open goes to the inspector; no Dismiss", async () => {
    const outreach = [{ job_id: "j-acme", company: "Acme Robotics", title: "Platform Engineer", contact_name: "Jane Doe",
      contact_role: "recruiter", email: "jane@acme.example", email_confidence: "low", draft_ready: true, followup_due: null }];
    const { container } = setup("/", { "GET /api/today": { ...today, outreach } });
    await screen.findByText(G);
    const heads = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(heads).toEqual(["Ready to send 1", "Reach out 1", "Everything else 3"]);
    const row = screen.getByText("Recruiter Jane Doe · email unconfirmed · draft ready").closest("li")!;
    expect(within(row).getByRole("link", { name: "Open" })).toHaveAttribute("href", "/?job=j-acme");
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("NeedsYou inline answer", () => {
  const q = actionItem({ id: "q1", company: "Globex", what: "Question: What is your visa status? Needed for the form.", type: "question", job_id: "j-globex" });
  const withQ = (): Routes => ({ "GET /api/today": { ...today, actions: [q] }, "POST /api/actions/q1/answer": json({ id: "q1" }) });

  it("shows the question and answers it in place", async () => {
    const { calls } = setup("/", withQ());
    const row = (await screen.findByText("What is your visa status?")).closest("li")!;
    expect(within(row).queryByRole("link")).not.toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: "Answer: Globex" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Your answer for Globex" }), "Citizen");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/actions/q1/answer")?.body).toEqual({ answer: "Citizen" }));
  });

  it("Esc cancels without posting", async () => {
    const { calls } = setup("/", withQ());
    await userEvent.click(await screen.findByRole("button", { name: "Answer: Globex" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("says a fill plan has questions only you can answer", async () => {
    setup("/", { "GET /api/today": { ...today, actions: [actionItem({ id: "q2", company: "Globex", what: "fill plan: abc12345", type: "question" })] } });
    expect(await screen.findByText("The form has questions only you can answer.")).toBeInTheDocument();
  });
});
