import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { type Call, SECTIONS, autonomyData, mockApi, renderSettings, route, runsData, safetyData, sectionRoutes } from "./testing";

afterEach(() => vi.unstubAllGlobals());

async function openAutonomy() {
  const calls = mockApi(...sectionRoutes(autonomyData()));
  const utils = renderSettings("/settings/autonomy");
  await screen.findByRole("heading", { name: "Volume" }, { timeout: 5000 });
  return { calls, ...utils };
}

describe("Settings navigation", () => {
  it("lists the sections in schema order and marks the current one", async () => {
    await openAutonomy();
    const nav = screen.getByRole("navigation", { name: "Settings sections" });
    const links = within(nav).getAllByRole("link");
    await waitFor(() => expect(links.length).toBeGreaterThan(0));
    expect(within(nav).getAllByRole("link").map((l) => l.textContent)).toEqual([
      "General",
      "Autonomy",
      "Safety",
      "Runs & schedule",
      "Storage & efficiency",
    ]);
    expect(within(nav).getByRole("link", { name: "Autonomy" })).toHaveAttribute("aria-current", "page");
  });

  it("/settings opens General", async () => {
    mockApi(...sectionRoutes(), route("GET", "/api/settings/general", { detail: "x" }, 404));
    const { router } = renderSettings("/settings");
    await waitFor(() => expect(router.state.location.pathname).toBe("/settings/general"));
  });

  it("an unknown section says so", async () => {
    mockApi(...sectionRoutes());
    renderSettings("/settings/nope");
    expect(await screen.findByRole("heading", { name: "No settings page here" })).toBeInTheDocument();
  });
});

describe("generic form", () => {
  it("renders controls with (Recommended) notes, policy rows and locked rows", async () => {
    await openAutonomy();
    const perDay = screen.getByRole("textbox", { name: "Applications per day" });
    expect(perDay).toHaveValue("12");
    expect(within(perDay.closest("[data-field]") as HTMLElement).getByText("Recommended: 15")).toBeInTheDocument();
    const cooldown = screen.getByRole("textbox", { name: "Cooldown after a rejection" });
    expect(within(cooldown.closest("[data-field]") as HTMLElement).getByText("Recommended")).toBeInTheDocument();
    expect(screen.getByText("Draft only")).toBeInTheDocument();
    const tierA = screen.getByRole("switch", { name: "Tier A: Auto-submit when you run Apply" });
    expect(tierA).toBeDisabled();
    expect(screen.getByText(/Tier A is never auto-submitted/)).toBeInTheDocument();
    expect(screen.getAllByRole("option", { name: "Always (Recommended)" }).length).toBeGreaterThan(0);
  });

  it("counts unsaved changes and discards them after a confirm", async () => {
    const user = userEvent.setup();
    await openAutonomy();
    const perDay = screen.getByRole("textbox", { name: "Applications per day" });
    await user.clear(perDay);
    await user.type(perDay, "20");
    await user.click(screen.getByRole("switch", { name: "Tailor by hand when you're already connected" }));
    expect(screen.getByText(/2 unsaved changes/)).toBeInTheDocument();
    expect(screen.getByText(/config\/pipeline\.yaml/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    const confirm = screen.getByRole("alertdialog", { name: /Discard 2 unsaved changes/ });
    await user.click(within(confirm).getByRole("button", { name: "Discard" }));
    expect(screen.getByText(/No unsaved changes/)).toBeInTheDocument();
    expect(perDay).toHaveValue("12");
  });

  it("saves every change at once with the version and the write header", async () => {
    const user = userEvent.setup();
    const calls = mockApi(
      ...sectionRoutes(autonomyData()),
      route("PUT", "/api/settings/autonomy", { old: {}, version: "v2" }),
    );
    renderSettings("/settings/autonomy");
    const perDay = await screen.findByRole("textbox", { name: "Applications per day" });
    await user.clear(perDay);
    await user.type(perDay, "20");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    const put = await waitFor(() => {
      const c = calls.find((x) => x.method === "PUT");
      expect(c).toBeDefined();
      return c!;
    });
    expect(put.body).toEqual({ changes: { "targets:volume.max_applications_per_day": 20 }, version: "v1" });
    expect(put.headers.get("X-CareerOS")).toBe("1");
    expect(await screen.findByText("Saved config/pipeline.yaml and config/targets.yaml.")).toBeInTheDocument();
  });

  it("on 422 shows the error under the field, focuses it and says how many to fix", async () => {
    const user = userEvent.setup();
    mockApi(
      ...sectionRoutes(autonomyData()),
      route(
        "PUT",
        "/api/settings/autonomy",
        {
          detail: "Fix 1 error to save.",
          fields: { "targets:volume.same_company_cooldown_days": "Must be at least 0." },
          general: [],
        },
        422,
      ),
    );
    renderSettings("/settings/autonomy");
    const cooldown = await screen.findByRole("textbox", { name: "Cooldown after a rejection" });
    await user.clear(cooldown);
    await user.type(cooldown, "-3");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Must be at least 0.")).toBeInTheDocument();
    await waitFor(() => expect(cooldown).toHaveFocus());
    expect(cooldown).toHaveAttribute("aria-invalid", "true");
    expect(cooldown).toHaveAccessibleDescription(/Must be at least 0\./);
    expect(screen.getByText(/fix 1 error to save/)).toBeInTheDocument();
    await user.type(cooldown, "0");
    expect(screen.queryByText("Must be at least 0.")).not.toBeInTheDocument();
  });

  it("checks an empty number in the browser without a request", async () => {
    const user = userEvent.setup();
    const { calls } = await openAutonomy();
    const perDay = screen.getByRole("textbox", { name: "Applications per day" });
    await user.clear(perDay);
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("A value is required.")).toBeInTheDocument();
    await waitFor(() => expect(perDay).toHaveFocus());
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("Reset to recommended fills the group's recommended values as unsaved edits", async () => {
    const user = userEvent.setup();
    const calls = mockApi(
      ...sectionRoutes(autonomyData()),
      route("POST", "/api/settings/autonomy/reset/volume", {
        changes: { "targets:volume.max_applications_per_day": 15, "targets:volume.same_company_cooldown_days": 30 },
      }),
    );
    renderSettings("/settings/autonomy");
    await screen.findByRole("heading", { name: "Volume" });
    await user.click(screen.getByRole("button", { name: "Reset to recommended: Volume" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Applications per day" })).toHaveValue("15"));
    expect(screen.getByText(/1 unsaved change/)).toBeInTheDocument();
    expect(calls.find((c) => c.url.endsWith("/reset/volume"))?.headers.get("X-CareerOS")).toBe("1");
    expect(screen.getByRole("button", { name: "Reset to recommended: Outreach" })).toBeDisabled();
  });

  it("Show diff opens a sheet with the file's diff", async () => {
    const user = userEvent.setup();
    mockApi(
      ...sectionRoutes(autonomyData()),
      route("POST", "/api/settings/autonomy/diff", {
        diffs: { targets: "--- a\n+++ b\n@@ -1 +1 @@\n-  max_applications_per_day: 12\n+  max_applications_per_day: 20" },
      }),
    );
    renderSettings("/settings/autonomy");
    const perDay = await screen.findByRole("textbox", { name: "Applications per day" });
    await user.clear(perDay);
    await user.type(perDay, "20");
    await user.click(screen.getByRole("button", { name: "Show diff" }));
    const sheet = await screen.findByRole("dialog", { name: "Changes a save writes" });
    expect(within(sheet).getByText("config/targets.yaml")).toBeInTheDocument();
    expect(within(sheet).getByText(/\+ max_applications_per_day: 20/)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("turning on auto-submit asks first; Cancel keeps it off", async () => {
    const user = userEvent.setup();
    await openAutonomy();
    const b = screen.getByRole("switch", { name: "Tier B: Auto-submit when you run Apply" });
    await user.click(b);
    const ask = screen.getByRole("alertdialog", { name: "Turn on auto-submit for Tier B?" });
    await user.click(within(ask).getByRole("button", { name: "Cancel" }));
    expect(b).toHaveAttribute("aria-checked", "false");
    await user.click(b);
    await user.click(screen.getByRole("button", { name: "Turn on" }));
    expect(b).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/1 unsaved change/)).toBeInTheDocument();
    // turning off needs no confirm
    await user.click(screen.getByRole("switch", { name: "Tier C: Auto-submit when you run Apply" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("guards leaving with unsaved changes", async () => {
    const user = userEvent.setup();
    const { router } = await openAutonomy();
    await user.click(screen.getByRole("switch", { name: "Tailor by hand when you're already connected" }));
    await act(() => router.navigate("/runs"));
    const guard = await screen.findByRole("alertdialog", { name: /Leave without saving\? 1 unsaved change/ });
    await user.click(within(guard).getByRole("button", { name: "Keep editing" }));
    expect(router.state.location.pathname).toBe("/settings/autonomy");
    await act(() => router.navigate("/runs"));
    await user.click(await screen.findByRole("button", { name: "Leave" }));
    expect(await screen.findByText("Runs page")).toBeInTheDocument();
  });

  it("keeps the version the drafts started from, so a save after a refetch still reports the conflict", async () => {
    const user = userEvent.setup();
    let version = "v1";
    const calls = mockApi(
      route("GET", "/api/settings", { sections: SECTIONS }),
      route("GET", "/api/settings/autonomy", () => ({ ...autonomyData(), version })),
      route("PUT", "/api/settings/autonomy", { detail: "The settings files changed since this page was opened; reload to see them." }, 409),
    );
    const { qc } = renderSettings("/settings/autonomy");
    const perDay = await screen.findByRole("textbox", { name: "Applications per day" });
    await user.clear(perDay);
    await user.type(perDay, "20");
    version = "v2";
    await act(() => qc.invalidateQueries({ queryKey: ["settings"] }));
    await waitFor(() => expect(calls.filter((c) => c.url === "/api/settings/autonomy").length).toBe(2));
    expect(perDay).toHaveValue("20");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    const put = await waitFor(() => calls.find((c) => c.method === "PUT")!);
    expect((put.body as { version: string }).version).toBe("v1");
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed since this page was opened/);
    // discard starts over from the fresh version
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Discard" }));
    await user.click(screen.getByRole("switch", { name: "Tailor by hand when you're already connected" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT").length).toBe(2));
    expect((calls.filter((c) => c.method === "PUT")[1]!.body as { version: string }).version).toBe("v2");
  });

  it("Reset to recommended asks before it turns auto-submit on; Cancel applies the other keys only", async () => {
    const user = userEvent.setup();
    mockApi(
      ...sectionRoutes(autonomyData()),
      route("POST", "/api/settings/autonomy/reset/tier_b", {
        changes: { "targets:tiers.B.auto_submit": true, "targets:tiers.B.cover_letter": "if_required" },
      }),
    );
    renderSettings("/settings/autonomy");
    const b = await screen.findByRole("switch", { name: "Tier B: Auto-submit when you run Apply" });
    await user.click(screen.getByRole("button", { name: "Reset to recommended: Tier B" }));
    const ask = await screen.findByRole("alertdialog", { name: "Turn on auto-submit for Tier B?" });
    await user.click(within(ask).getByRole("button", { name: "Cancel" }));
    expect(b).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("combobox", { name: "Tier B: Cover letter" })).toHaveValue("if_required");
    expect(screen.getByText(/1 unsaved change/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset to recommended: Tier B" }));
    await user.click(await screen.findByRole("button", { name: "Turn on" }));
    expect(b).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/2 unsaved changes/)).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = await openAutonomy();
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("Safety and Runs pages", () => {
  it("reason codes get a level select with a built-in option; tags add and remove", async () => {
    const user = userEvent.setup();
    mockApi(...sectionRoutes(safetyData()));
    renderSettings("/settings/safety");
    const old = await screen.findByRole("combobox", { name: "Level for Posting is old" });
    expect(old).toHaveValue("info");
    const pay = screen.getByRole("combobox", { name: "Level for Posting asks you to pay" });
    expect(pay).toHaveValue("");
    await user.selectOptions(pay, "block");
    await user.click(screen.getByRole("button", { name: "Remove Lever" }));
    expect(screen.getByText(/2 unsaved changes/)).toBeInTheDocument();
  });

  it("budget presets are a radio group; limits unlock only for Custom", async () => {
    const user = userEvent.setup();
    mockApi(...sectionRoutes(runsData()));
    renderSettings("/settings/runs");
    const group = await screen.findByRole("radiogroup", { name: "Preset" });
    const medium = within(group).getByRole("radio", { name: /Medium/ });
    expect(medium).toHaveAttribute("aria-checked", "true");
    expect(medium).toHaveTextContent("Recommended");
    const scored = screen.getByRole("textbox", { name: "Jobs scored per run" });
    expect(scored).toHaveAttribute("readonly");
    medium.focus();
    await user.keyboard("{ArrowRight}");
    expect(within(group).getByRole("radio", { name: /Custom/ })).toHaveAttribute("aria-checked", "true");
    expect(scored).not.toHaveAttribute("readonly");
  });

  it("the ranking preview says why it's missing when the server can't rank", async () => {
    mockApi(...sectionRoutes(runsData()));
    renderSettings("/settings/runs");
    expect(await screen.findByText(/The preview isn't available right now/)).toBeInTheDocument();
  });

  it("the ranking preview lists the next jobs for the draft weights", async () => {
    const user = userEvent.setup();
    const calls = mockApi(
      ...sectionRoutes(runsData()),
      route("POST", "/api/settings/runs/ranking-preview", (c: Call) => ({
        kind: "score",
        total: 7,
        items: [
          {
            job_id: "j1",
            company: "Acme Robotics",
            title: "Backend Engineer",
            score: (c.body as { weights: { freshness_weight: number } }).weights.freshness_weight,
            why: "posted 3h ago",
            rank: 1,
          },
        ],
      })),
    );
    renderSettings("/settings/runs");
    expect(await screen.findByText("Acme Robotics")).toBeInTheDocument();
    expect(screen.getByText("Top 1 of 7 waiting.", { exact: false })).toBeInTheDocument();
    const fresh = screen.getByRole("textbox", { name: "Fresh for" });
    await user.clear(fresh);
    await user.type(fresh, "24");
    await waitFor(() =>
      expect(calls.some((c) => c.url.endsWith("ranking-preview") && (c.body as { weights: Record<string, number> }).weights.fresh_hours === 24)).toBe(true),
    );
    expect(screen.getByRole("heading", { name: "Preview with these weights" })).toBeInTheDocument();
  });

  it("read-only rows show why; schedules and quiet hours edit their blocks", async () => {
    const user = userEvent.setup();
    mockApi(...sectionRoutes(runsData()));
    renderSettings("/settings/runs");
    const sched = await screen.findByRole("switch", { name: "Scheduled runs may submit" });
    expect(sched).toBeDisabled();
    expect(screen.getAllByText(/Runs never apply in this version/).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("switch", { name: "Score schedule" }));
    await user.click(screen.getByRole("switch", { name: "Quiet hours" }));
    expect(screen.getByText(/2 unsaved changes/)).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "Score: how often" }), "every_hours");
    expect(screen.getByRole("textbox", { name: "Score: every how many hours" })).toHaveValue("3");
  });
});
