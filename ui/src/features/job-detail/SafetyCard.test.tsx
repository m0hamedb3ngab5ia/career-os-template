import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../../test/apiMock";
import { axeViolations } from "../../test/axe";
import { detail } from "./fixtures";
import { SafetyCard } from "./SafetyCard";
import { renderWithProviders } from "./testUtils";
import type { Registry } from "./types";

const d = detail();

function renderCard(registry: Registry = { verified: null, flagged: null }, extra = {}) {
  const api = mockApi({
    "POST /api/jobs/nw01/safety/verify": { company: "Northwind Labs", risk: "low" },
    "POST /api/jobs/nw01/safety/flag": { company: "Northwind Labs" },
    "POST /api/jobs/nw01/safety/clear": { state: "cleared" },
    ...extra,
  });
  const utils = renderWithProviders(
    <SafetyCard jobId="nw01" company="Northwind Labs" tier="A" safety={d.safety} registry={registry} />,
  );
  return { api, ...utils };
}

afterEach(() => vi.unstubAllGlobals());

describe("SafetyCard", () => {
  it("shows the verdict, Tier A note and flags in plain language with code, level and detail", () => {
    renderCard();
    const card = screen.getByRole("region", { name: "Safety" });
    expect(within(card).getByText("Pass")).toHaveAttribute("data-tone", "green");
    expect(within(card).getByText(/Tier A is always you-submit/)).toBeInTheDocument();
    expect(within(card).getByText("Old posting")).toBeInTheDocument();
    expect(within(card).getByText("Posted 12 days ago")).toBeInTheDocument();
    expect(within(card).getByText("GHOST_OLD_POST")).toBeInTheDocument();
    expect(within(card).getByText("New code x")).toBeInTheDocument();
    expect(within(card).getByText(/Checked 2 times/)).toBeInTheDocument();
    // Clear only shows when the registry has an active flag
    expect(within(card).queryByRole("button", { name: /Clear flag/ })).not.toBeInTheDocument();
    // flags without evidence get no Evidence button
    expect(within(card).getAllByRole("button", { name: /^Evidence/ })).toHaveLength(1);
  });

  it("Evidence opens a dialog of links; Escape closes it and returns focus", async () => {
    const user = userEvent.setup();
    renderCard();
    const btn = screen.getByRole("button", { name: "Evidence for old posting" });
    await user.click(btn);
    const dlg = screen.getByRole("dialog", { name: "Evidence: Old posting" });
    expect(within(dlg).getByRole("link", { name: /example.com\/northwind/ })).toHaveAttribute("target", "_blank");
    expect(within(dlg).getByText("ATS shows first published date")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(btn).toHaveFocus();
  });

  it("Verify company: low risk needs two signals, then posts risk, signals, evidence and domain", async () => {
    const user = userEvent.setup();
    const { api } = renderCard();
    await user.click(screen.getByRole("button", { name: "Verify company" }));
    const sheet = screen.getByRole("dialog", { name: "Verify Northwind Labs" });
    expect(within(sheet).getByRole("radio", { name: /Low/ })).toBeChecked();
    const signals = within(sheet).getByRole("textbox", { name: "Signals" });
    await user.type(signals, "Careers page lists the role");
    await user.click(within(sheet).getByRole("button", { name: "Save verification" }));
    expect(signals).toHaveAttribute("aria-invalid", "true");
    expect(signals).toHaveAccessibleDescription(/Low risk needs at least two signals/);
    expect(signals).toHaveFocus();
    expect(api.callsTo("POST /api/jobs/nw01/safety/verify")).toHaveLength(0);
    await user.type(signals, "{Enter}Company domain matches the ATS");
    await user.type(within(sheet).getByRole("textbox", { name: /Evidence links/ }), "https://example.com/about");
    await user.type(within(sheet).getByRole("textbox", { name: /Domain/ }), "example.com");
    await user.click(within(sheet).getByRole("button", { name: "Save verification" }));
    expect(await screen.findByText("Marked Northwind Labs as verified (low risk)")).toBeInTheDocument();
    const call = api.callsTo("POST /api/jobs/nw01/safety/verify")[0]!;
    expect(call.headers["x-careeros"]).toBe("1");
    expect(call.body).toEqual({
      risk: "low",
      signals: ["Careers page lists the role", "Company domain matches the ATS"],
      evidence: ["https://example.com/about"],
      domain: "example.com",
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Verify shows the server's 400 detail and keeps the sheet open", async () => {
    const user = userEvent.setup();
    renderCard(undefined, {
      "POST /api/jobs/nw01/safety/verify": { status: 400, body: { detail: "high risk needs a reason" } },
    });
    await user.click(screen.getByRole("button", { name: "Verify company" }));
    const sheet = screen.getByRole("dialog");
    await user.click(within(sheet).getByRole("radio", { name: "High" }));
    await user.click(within(sheet).getByRole("button", { name: "Save verification" }));
    expect(await screen.findByText("high risk needs a reason")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("Flag as suspicious posts reason, confidence and evidence", async () => {
    const user = userEvent.setup();
    const { api } = renderCard();
    await user.click(screen.getByRole("button", { name: "Flag as suspicious" }));
    const sheet = screen.getByRole("dialog", { name: "Flag Northwind Labs as suspicious" });
    await user.type(within(sheet).getByRole("textbox", { name: "Reason" }), "Asked for a fee");
    await user.click(within(sheet).getByRole("radio", { name: /High/ }));
    await user.type(within(sheet).getByRole("textbox", { name: /Evidence links/ }), "https://example.com/post");
    await user.click(within(sheet).getByRole("button", { name: "Flag company" }));
    expect(await screen.findByText("Flagged Northwind Labs as suspicious")).toBeInTheDocument();
    expect(api.callsTo("POST /api/jobs/nw01/safety/flag")[0]!.body).toEqual({
      reason: "Asked for a fee",
      confidence: "high",
      evidence: ["https://example.com/post"],
    });
  });

  it("Clear (active flag only) asks first, then posts", async () => {
    const user = userEvent.setup();
    const { api } = renderCard({
      verified: null,
      flagged: { company: "Northwind Labs", reason: "Fee request", confidence: "high", state: "active" },
    });
    expect(screen.getByText(/Flagged as suspicious: Fee request/)).toBeInTheDocument();
    const clear = screen.getByRole("button", { name: "Clear flag…" });
    await user.click(clear);
    const confirm = screen.getByRole("alertdialog", { name: "Clear the flag on Northwind Labs?" });
    await user.keyboard("{Escape}");
    expect(confirm).not.toBeInTheDocument();
    expect(clear).toHaveFocus();
    await user.click(clear);
    await user.click(screen.getByRole("button", { name: "Clear flag" }));
    expect(await screen.findByText("Cleared the flag on Northwind Labs")).toBeInTheDocument();
    expect(api.callsTo("POST /api/jobs/nw01/safety/clear")).toHaveLength(1);
  });

  it("a cleared registry entry shows no Clear button", () => {
    renderCard({ verified: null, flagged: { company: "Northwind Labs", state: "cleared" } });
    expect(screen.queryByRole("button", { name: /Clear flag/ })).not.toBeInTheDocument();
  });

  it("has no axe violations, with a sheet open too", { timeout: 20_000 }, async () => {
    const user = userEvent.setup();
    const { container } = renderCard();
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Verify company" }));
    expect(await axeViolations(document.body)).toEqual([]);
  });
});
