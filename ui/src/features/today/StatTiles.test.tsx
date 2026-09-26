import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../../test/axe";
import { StatTiles } from "./StatTiles";
import { NOW, status } from "./testing";
import type { Tiles } from "./types";

function setup(tiles: Tiles = status.tiles!) {
  return render(
    <MemoryRouter>
      <StatTiles tiles={tiles} now={NOW} />
      <button type="button">Elsewhere</button>
    </MemoryRouter>,
  );
}
const tile = (name: RegExp) => screen.getByRole("button", { name });

describe("StatTiles", () => {
  it("shows the four tiles with values and their secondary lines from the data", () => {
    setup();
    expect(tile(/Applied this week/)).toHaveTextContent("2");
    expect(tile(/Applied this week/)).toHaveTextContent("Limit: 15 a day");
    expect(tile(/Needs you/)).toHaveTextContent("4");
    expect(tile(/Needs you/)).toHaveTextContent("2 high priority");
    expect(tile(/Interviews/)).toHaveTextContent("Globex");
    expect(tile(/Response rate/)).toHaveTextContent("17%");
    expect(tile(/Response rate/)).toHaveTextContent("7 replies from 41 · 30 days");
  });

  it("shows — when the response rate is unknown and leaves out a missing daily cap", () => {
    setup({
      ...status.tiles,
      applied_week: { value: 0, rows: [], daily_cap: null },
      response_rate: { rate: null, responded: 0, applied: 0, days: 30, rows: [] },
    });
    expect(tile(/Response rate/)).toHaveTextContent("—");
    expect(tile(/Applied this week/)).not.toHaveTextContent("Limit");
  });

  it("opens one popover at a time with aria-expanded and aria-controls", async () => {
    const user = userEvent.setup();
    setup();
    const applied = tile(/Applied this week/);
    expect(applied).toHaveAttribute("aria-expanded", "false");
    await user.click(applied);
    expect(applied).toHaveAttribute("aria-expanded", "true");
    const pop = screen.getByRole("dialog", { name: "Applied this week" });
    expect(applied).toHaveAttribute("aria-controls", pop.id);
    expect(within(pop).getByText("Umbrella Labs")).toBeInTheDocument();
    expect(within(pop).getByRole("link", { name: "All jobs" })).toHaveAttribute("href", "/jobs");

    await user.click(tile(/Interviews/));
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.getByRole("dialog", { name: "Interviews" })).toBeInTheDocument();
    expect(applied).toHaveAttribute("aria-expanded", "false");

    await user.click(tile(/Interviews/));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Escape closes the popover and returns focus to its tile; outside clicks close it", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(tile(/Needs you/));
    expect(screen.getByRole("dialog", { name: "Needs you" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(tile(/Needs you/)).toHaveFocus();

    await user.click(tile(/Needs you/));
    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("the close button closes and returns focus", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(tile(/Interviews/));
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(tile(/Interviews/)).toHaveFocus();
  });

  it("response rate popover lists the breakdown and the definition, and links to the pipeline", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(tile(/Response rate/));
    const pop = screen.getByRole("dialog", { name: "Response rate" });
    expect(within(pop).getByText("7 replies from 41 applications in the last 30 days")).toBeInTheDocument();
    expect(within(pop).getByText("Interview")).toBeInTheDocument();
    expect(within(pop).getByText("Globex, Hooli")).toBeInTheDocument();
    expect(within(pop).getByText("No reply yet")).toBeInTheDocument();
    expect(within(pop).getByText("34")).toBeInTheDocument();
    expect(
      within(pop).getByText("Applications in the last 30 days that reached screening, interview, offer or rejected"),
    ).toBeInTheDocument();
    expect(within(pop).getByRole("link", { name: "Pipeline" })).toHaveAttribute("href", "/pipeline");
  });

  it("needs you and interviews popovers link to Action Items and Inbox; more rows than shown say so", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(tile(/Needs you/));
    let pop = screen.getByRole("dialog", { name: "Needs you" });
    expect(within(pop).getByText("Acme Robotics")).toBeInTheDocument();
    expect(within(pop).getByText("+2 more")).toBeInTheDocument();
    expect(within(pop).getByRole("link", { name: "Action Items" })).toHaveAttribute("href", "/actions");
    await user.click(tile(/Interviews/));
    pop = screen.getByRole("dialog", { name: "Interviews" });
    expect(within(pop).getByRole("link", { name: "Inbox" })).toHaveAttribute("href", "/inbox");
  });

  it("an empty tile's popover says so plainly, never invents rows", async () => {
    const user = userEvent.setup();
    setup({ ...status.tiles, interviews: { value: 0, rows: [] } });
    expect(tile(/Interviews/)).toHaveTextContent("None yet");
    await user.click(tile(/Interviews/));
    const pop = screen.getByRole("dialog", { name: "Interviews" });
    expect(within(pop).getByText("Nothing here yet.")).toBeInTheDocument();
    expect(within(pop).queryAllByRole("listitem")).toHaveLength(0);
  });

  it("has no axe violations, closed or open", async () => {
    const user = userEvent.setup();
    const { container } = setup();
    expect(await axeViolations(container)).toEqual([]);
    await user.click(tile(/Response rate/));
    expect(await axeViolations(container)).toEqual([]);
  });
});
