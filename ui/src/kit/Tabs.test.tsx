import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../test/axe";
import { Tabs } from "./Tabs";

function Demo() {
  const [v, setV] = useState("active");
  return (
    <>
      <Tabs label="Filter jobs" value={v} onValueChange={setV} controls="panel">
        <Tabs.Tab value="active" count={59}>Active</Tabs.Tab>
        <Tabs.Tab value="review" count={6}>Needs review</Tabs.Tab>
        <Tabs.Tab value="all">All</Tabs.Tab>
      </Tabs>
      <div id="panel" role="tabpanel" aria-label="Jobs">{v}</div>
    </>
  );
}

describe("Tabs", () => {
  it("is a tablist with one tab stop; arrows, Home and End move and select", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    const tabs = screen.getAllByRole("tab");
    expect(screen.getByRole("tablist", { name: "Filter jobs" })).toBeInTheDocument();
    expect(tabs.map((t) => t.getAttribute("tabindex"))).toEqual(["0", "-1", "-1"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[0]).toHaveAttribute("aria-controls", "panel");
    expect(tabs[0]).toHaveTextContent("Active (59)");
    tabs[0]!.focus();
    await user.keyboard("{ArrowRight}");
    expect(tabs[1]).toHaveFocus();
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(tabs[2]).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(tabs[0]).toHaveFocus();
    await user.keyboard("{ArrowLeft}{Home}");
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("active");
  });

  it("has no axe violations", async () => {
    const { container } = render(<Demo />);
    expect(await axeViolations(container)).toEqual([]);
  });
});
