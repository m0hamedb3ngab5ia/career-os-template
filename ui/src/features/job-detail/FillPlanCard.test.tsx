import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FillPlanCard } from "./FillPlanCard";
import { renderWithProviders } from "./testUtils";

const plan = {
  fields: [
    { field_id: "email", label: "Email", type: "text", value: "a@example.com", source: "profile", required: true },
    { field_id: "q1", label: "Notice period", type: "text", value: null, source: "unanswered", required: true },
    { field_id: "q2", label: "Editor", type: "text", value: null, source: "unanswered", required: false },
    { field_id: "q3", label: "Sponsorship?", type: "select", value: null, source: "pause:legal", required: true, options: ["Yes", "No"] },
  ],
};

function stubFetch(reply: unknown) {
  const calls: { url: string; body?: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body as string | undefined });
      const r = init?.method === "POST" ? { field: plan.fields[1], saved: true, problems: [] } : reply;
      return new Response(JSON.stringify(r), { status: 200, headers: { "content-type": "application/json" } });
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("FillPlanCard", () => {
  it("offers Preview fill before there is a plan", async () => {
    stubFetch({ plan: null, problems: [] });
    renderWithProviders(<FillPlanCard jobId="nw01" />);
    expect(await screen.findByRole("button", { name: "Preview fill" })).toBeEnabled();
  });

  it("shows label, value, source and required; blocks on required unknowns; saves an edit to the profile", async () => {
    const calls = stubFetch({ plan, problems: ["unanswered (pause:legal): Sponsorship?", "needs input (required): Notice period"] });
    renderWithProviders(<FillPlanCard jobId="nw01" />);
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getByRole("rowheader").textContent)).toEqual(["Email", "Notice period", "Editor", "Sponsorship?"]);
    expect(within(rows[0]!).getByText("Résumé / profile")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Needs input")).toBeInTheDocument();
    expect(within(rows[3]!).getByText("Your answer needed (legal)")).toBeInTheDocument();
    expect(screen.getByText("Fill application waits until you answer: Sponsorship?; Notice period")).toBeInTheDocument();
    expect(within(rows[1]!).queryByRole("button", { name: "Skip" })).toBeNull(); // required: no skip
    expect(within(rows[2]!).getByRole("button", { name: "Skip" })).toBeEnabled();
    await userEvent.type(within(rows[1]!).getByRole("textbox", { name: "Notice period" }), "4 weeks");
    expect(within(rows[1]!).getByRole("checkbox", { name: "Save to profile" })).toBeChecked();
    await userEvent.click(within(rows[1]!).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/fill-plan/fields/q1"))).toBe(true));
    const post = calls.find((c) => c.url.endsWith("/fill-plan/fields/q1"))!;
    expect(JSON.parse(post.body!)).toEqual({ value: "4 weeks", save: true });
    expect(await screen.findByText("Saved: Notice period, also saved to your profile")).toBeInTheDocument();
  });

  it("never offers Save to profile for an EEO row, even after an edit; salary is job-only by default", async () => {
    const calls = stubFetch({
      plan: {
        fields: [
          { field_id: "gender", label: "Gender", type: "text", value: "x", source: "user", kind: "eeo", required: false },
          { field_id: "pay", label: "Desired salary", type: "text", value: null, source: "pause:salary", kind: "salary", required: false },
        ],
      },
      problems: [],
    });
    renderWithProviders(<FillPlanCard jobId="nw01" />);
    const rows = within(await screen.findByRole("table")).getAllByRole("row").slice(1);
    expect(within(rows[0]!).queryByRole("checkbox", { name: "Save to profile" })).toBeNull();
    expect(within(rows[1]!).getByRole("checkbox", { name: "Save to profile" })).not.toBeChecked();
    await userEvent.type(within(rows[0]!).getByRole("textbox", { name: "Gender" }), "y");
    await userEvent.click(within(rows[0]!).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/fields/gender"))).toBe(true));
    expect(JSON.parse(calls.find((c) => c.url.endsWith("/fields/gender"))!.body!)).toEqual({ value: "xy", save: false });
  });
});
