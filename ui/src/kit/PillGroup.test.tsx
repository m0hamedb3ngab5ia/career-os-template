import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { axeViolations } from "../test/axe";
import { PillGroup } from "./PillGroup";

function Demo({ onChange }: { onChange?: (v: string) => void }) {
  const [v, setV] = useState("all");
  return (
    <PillGroup
      label="Filter"
      value={v}
      onValueChange={(x) => {
        setV(x);
        onChange?.(x);
      }}
    >
      <PillGroup.Pill value="all">All</PillGroup.Pill>
      <PillGroup.Pill value="overdue">Overdue</PillGroup.Pill>
      <PillGroup.Pill value="high">High priority</PillGroup.Pill>
    </PillGroup>
  );
}

describe("PillGroup", () => {
  it("is a labelled radio group with one checked pill and one tab stop", () => {
    render(<Demo />);
    const group = screen.getByRole("radiogroup", { name: "Filter" });
    expect(group).toBeInTheDocument();
    const all = screen.getByRole("radio", { name: "All" });
    expect(all).toHaveAttribute("aria-checked", "true");
    expect(all).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("radio", { name: "Overdue" })).toHaveAttribute("tabindex", "-1");
  });

  it("selects on click", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Demo onChange={onChange} />);
    await user.click(screen.getByRole("radio", { name: "High priority" }));
    expect(onChange).toHaveBeenCalledWith("high");
    expect(screen.getByRole("radio", { name: "High priority" })).toHaveAttribute("aria-checked", "true");
  });

  it("moves and selects with arrow keys, Home and End (roving tabindex, wraps)", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    screen.getByRole("radio", { name: "All" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Overdue" })).toHaveFocus();
    expect(screen.getByRole("radio", { name: "Overdue" })).toHaveAttribute("aria-checked", "true");
    await user.keyboard("{End}");
    expect(screen.getByRole("radio", { name: "High priority" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "All" })).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "High priority" })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(screen.getByRole("radio", { name: "All" })).toHaveAttribute("aria-checked", "true");
  });

  it("has no axe violations", async () => {
    const { container } = render(<Demo />);
    expect(await axeViolations(container)).toEqual([]);
  });
});
