import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, type Call, type Routes } from "../../test/apiMock";
import { axeViolations } from "../../test/axe";
import { renderApp } from "../../test/renderApp";
import { META } from "../jobs/fixtures";
import { detail } from "./fixtures";

function setup(routes: Routes = {}, path = "/jobs/nw01") {
  const api = mockApi({
    "GET /api/status": {},
    "GET /api/meta": META,
    "GET /api/jobs/nw01": detail(),
    "POST /api/jobs/nw01/status": (c: Call) => ({ status: (c.body as { status: string }).status, previous: "needs_review" }),
    "POST /api/jobs/nw01/override": (c: Call) => ({ override: (c.body as { value: string }).value }),
    "POST /api/jobs/nw01/withdraw": { status: "withdrawn", previous: "needs_review" },
    "POST /api/jobs/nw01/submitted": { status: "applied", previous: "needs_review" },
    ...routes,
  });
  return { api, ...renderApp(path) };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Job detail screen", () => {
  it("shows the company, breadcrumb, tier/status subtitle, posting and progress", async () => {
    setup();
    expect(await screen.findByRole("heading", { level: 1, name: "Northwind Labs" }, { timeout: 5000 })).toBeInTheDocument();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getByRole("link", { name: "Jobs" })).toHaveAttribute("href", "/jobs");
    expect(within(crumbs).getByText("Northwind Labs")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("· Tier A")).toBeInTheDocument();
    const posting = screen.getByRole("region", { name: "Posting" });
    expect(within(posting).getByRole("heading", { name: "Software Engineer, Infrastructure" })).toBeInTheDocument();
    expect(within(posting).getByRole("link", { name: /Open posting on Greenhouse/ })).toHaveAttribute(
      "href",
      "https://example.com/northwind/jobs/1",
    );
    expect(within(posting).getByText("nw01")).toBeInTheDocument();
    const progress = await screen.findByRole("list", { name: "Application progress" });
    expect(within(progress).getByText("Needs review").closest("li")).toHaveAttribute("aria-current", "step");
    for (const name of ["Safety", "Score", "Documents", "Contacts & outreach", "Apply session", "Activity"]) {
      expect(screen.getByRole("region", { name })).toBeInTheDocument();
    }
    expect(document.title).toBe("Northwind Labs · career-os");
  });

  it("Set status never offers applied: that goes only through the confirmed Mark submitted path", async () => {
    setup();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Set status" }));
    const menu = screen.getByRole("menu", { name: "Set status" });
    expect(within(menu).queryByRole("menuitemradio", { name: "Applied" })).not.toBeInTheDocument();
  });

  it("Set status: a menu of meta.statuses; picking one posts it and offers Undo", async () => {
    const { api } = setup();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Set status" }));
    const menu = screen.getByRole("menu", { name: "Set status" });
    expect(within(menu).getAllByRole("menuitemradio")).toHaveLength(META.statuses.filter((x) => x !== "applied").length);
    expect(within(menu).getByRole("menuitemradio", { name: "Needs review" })).toHaveAttribute("aria-checked", "true");
    expect(within(menu).getByRole("menuitemradio", { name: "Needs review" })).toHaveFocus();
    await user.click(within(menu).getByRole("menuitemradio", { name: "Interview" }));
    expect(await screen.findByText("Status set to Interview")).toBeInTheDocument();
    expect(api.callsTo("POST /api/jobs/nw01/status")[0]!.body).toEqual({ status: "interview" });
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(api.callsTo("POST /api/jobs/nw01/status")).toHaveLength(2));
    expect(api.callsTo("POST /api/jobs/nw01/status")[1]!.body).toEqual({
      status: "needs_review",
      note: "undo status change",
    });
  });

  it("Set status Undo restores applied when the job was applied before", async () => {
    const { api } = setup({
      "POST /api/jobs/nw01/status": (c: Call) => ({ status: (c.body as { status: string }).status, previous: "applied" }),
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Set status" }));
    await user.click(within(screen.getByRole("menu", { name: "Set status" })).getByRole("menuitemradio", { name: "Interview" }));
    await user.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(api.callsTo("POST /api/jobs/nw01/status")).toHaveLength(2));
    expect(api.callsTo("POST /api/jobs/nw01/status")[1]!.body).toEqual({ status: "applied", note: "undo status change" });
  });

  it("Status override: says when Excel holds the tracker and the change is queued", async () => {
    setup({ "POST /api/jobs/nw01/override": (c: Call) => ({ override: (c.body as { value: string }).value, queued: true }) });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Status override: none" }));
    await user.click(screen.getByRole("menuitemradio", { name: /skip/i }));
    expect(await screen.findByText(/saved to a queue; it's written on the next change, or run `careeros tracker flush` after closing Excel/)).toBeInTheDocument();
  });

  it("Status override: reads the value and posts the choice", async () => {
    const { api } = setup({ "GET /api/jobs/nw01": detail({ override: "B" }) });
    const user = userEvent.setup();
    const btn = await screen.findByRole("button", { name: "Status override: B" });
    await user.click(btn);
    await user.click(screen.getByRole("menuitemradio", { name: "None" }));
    await waitFor(() => expect(api.callsTo("POST /api/jobs/nw01/override")).toHaveLength(1));
    expect(api.callsTo("POST /api/jobs/nw01/override")[0]!.body).toEqual({ value: "" });
    expect(btn).toHaveFocus();
  });

  it("override none reads 'none'", async () => {
    setup();
    expect(await screen.findByRole("button", { name: "Status override: none" })).toBeInTheDocument();
  });

  it("Withdraw… confirms inline, posts, and Undo restores the previous status within undo_seconds", async () => {
    const { api } = setup();
    const user = userEvent.setup();
    const btn = await screen.findByRole("button", { name: "Withdraw…" });
    await user.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    const confirm = screen.getByRole("alertdialog", { name: "Withdraw from Northwind Labs?" });
    expect(confirm).toHaveAccessibleDescription(/Your documents stay in the job folder/);
    expect(within(confirm).getByRole("button", { name: "Keep application" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(btn).toHaveFocus();
    expect(api.callsTo("POST /api/jobs/nw01/withdraw")).toHaveLength(0);

    await user.click(btn);
    await user.click(screen.getByRole("button", { name: "Withdraw" }));
    expect(await screen.findByText("Application withdrawn")).toBeInTheDocument();
    expect(api.callsTo("POST /api/jobs/nw01/withdraw")[0]!.headers["x-careeros"]).toBe("1");
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() =>
      expect(api.callsTo("POST /api/jobs/nw01/status")[0]!.body).toEqual({
        status: "needs_review",
        note: "undo withdraw",
      }),
    );
  });

  it("Mark submitted asks first, then posts", async () => {
    const { api } = setup();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Mark submitted" }));
    const confirm = screen.getByRole("alertdialog", { name: "Mark Northwind Labs as submitted?" });
    expect(api.callsTo("POST /api/jobs/nw01/submitted")).toHaveLength(0);
    await user.click(within(confirm).getByRole("button", { name: "Mark submitted" }));
    expect(await screen.findByText("Marked Northwind Labs as submitted")).toBeInTheDocument();
    await waitFor(() => expect(api.callsTo("POST /api/jobs/nw01/submitted")).toHaveLength(1));
  });

  it("errors show the server's detail in a toast", async () => {
    setup({ "POST /api/jobs/nw01/status": { status: 409, body: { detail: "Excel has the tracker open" } } });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Set status" }));
    await user.click(screen.getByRole("menuitemradio", { name: "Offer" }));
    expect(await screen.findByText("Excel has the tracker open")).toBeInTheDocument();
  });

  it("a closed job shows a terminal step and no Withdraw or Mark submitted", async () => {
    setup({
      "GET /api/jobs/nw01": detail({
        status: "rejected",
        history: [
          { status: "applied", at: "2026-09-10T10:00:00" },
          { status: "rejected", at: "2026-09-20T10:00:00" },
        ],
      }),
    });
    const progress = await screen.findByRole("list", { name: "Application progress" });
    const items = within(progress).getAllByRole("listitem");
    expect(items.at(-1)).toHaveTextContent("Current step: Rejected");
    expect(items.at(-2)).toHaveTextContent("Done: Applied");
    expect(screen.queryByRole("button", { name: "Withdraw…" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark submitted" })).not.toBeInTheDocument();
  });

  it("404 shows not found with a way back to Jobs", async () => {
    setup({ "GET /api/jobs/zz99": { status: 404, body: { detail: "unknown job" } } }, "/jobs/zz99");
    expect(await screen.findByRole("heading", { level: 1, name: "Job not found" }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Jobs" })).toHaveAttribute("href", "/jobs");
  });

  it("has no axe violations", { timeout: 20_000 }, async () => {
    const { container } = setup();
    await screen.findByRole("list", { name: "Application progress" });
    await act(async () => undefined);
    expect(await axeViolations(container)).toEqual([]);
  });
});
