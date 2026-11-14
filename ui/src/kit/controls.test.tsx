import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../test/axe";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { Popover } from "./Popover";
import { SegmentedControl } from "./SegmentedControl";

describe("Button", () => {
  it("renders variants and keeps the label with an ellipsis while pending", () => {
    const { rerender } = render(<Button variant="primary">Save changes</Button>);
    const b = screen.getByRole("button", { name: "Save changes" });
    expect(b).toHaveAttribute("data-variant", "primary");
    expect(b).toBeEnabled();
    rerender(
      <Button variant="primary" pending pendingLabel="Saving…">
        Save changes
      </Button>,
    );
    const p = screen.getByRole("button", { name: "Saving…" });
    expect(p).toBeDisabled();
    expect(p).toHaveAttribute("aria-busy", "true");
  });

  it("defaults to type=button so it never submits a form by accident", () => {
    render(<Button>Run scout</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });
});

describe("SegmentedControl", () => {
  function Demo({ onChange }: { onChange?: (v: string) => void }) {
    const [v, setV] = useState("priority");
    return (
      <SegmentedControl
        label="Sort"
        value={v}
        onValueChange={(nv) => {
          setV(nv);
          onChange?.(nv);
        }}
      >
        <SegmentedControl.Option value="priority">Priority</SegmentedControl.Option>
        <SegmentedControl.Option value="due">Due date</SegmentedControl.Option>
        <SegmentedControl.Option value="az">A–Z</SegmentedControl.Option>
      </SegmentedControl>
    );
  }

  it("uses a roving tabindex and arrow keys select and focus", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    const group = screen.getByRole("radiogroup", { name: "Sort" });
    const radios = screen.getAllByRole("radio");
    expect(group).toBeInTheDocument();
    expect(radios.map((r) => r.getAttribute("tabindex"))).toEqual(["0", "-1", "-1"]);
    radios[0]!.focus();
    await user.keyboard("{ArrowRight}");
    expect(radios[1]).toHaveFocus();
    expect(radios[1]).toHaveAttribute("aria-checked", "true");
    await user.keyboard("{End}");
    expect(radios[2]).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(radios[0]).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(radios[2]).toHaveFocus();
    await user.keyboard("{Home}");
    expect(radios[0]).toHaveAttribute("aria-checked", "true");
  });

  it("skips disabled options with arrow keys and links the reason", async () => {
    const user = userEvent.setup();
    function D() {
      const [v, setV] = useState("a");
      return (
        <>
          <SegmentedControl label="Stop" value={v} onValueChange={setV}>
            <SegmentedControl.Option value="a">A</SegmentedControl.Option>
            <SegmentedControl.Option value="b" disabled describedBy="why">B</SegmentedControl.Option>
            <SegmentedControl.Option value="c">C</SegmentedControl.Option>
          </SegmentedControl>
          <p id="why">B is off in Settings</p>
        </>
      );
    }
    render(<D />);
    const [a, b, c] = screen.getAllByRole("radio");
    expect(b).toBeDisabled();
    expect(b).toHaveAccessibleDescription("B is off in Settings");
    a!.focus();
    await user.keyboard("{ArrowRight}");
    expect(c).toHaveFocus();
    expect(c).toHaveAttribute("aria-checked", "true");
    await user.keyboard("{ArrowLeft}");
    expect(a).toHaveFocus();
  });

  it("has no axe violations", async () => {
    const { container } = render(<Demo />);
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("Popover", () => {
  function Demo() {
    const [open, setOpen] = useState(false);
    const anchor = useRef<HTMLButtonElement>(null);
    return (
      <>
        <button ref={anchor} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          Applied this week
        </button>
        <button>Elsewhere</button>
        <Popover open={open} onClose={() => setOpen(false)} anchorRef={anchor} label="Applied this week">
          <p>9 applications</p>
          <button>Open jobs</button>
        </Popover>
      </>
    );
  }

  it("opens as a labelled dialog, Escape closes and returns focus to the anchor", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    const anchor = screen.getByRole("button", { name: "Applied this week" });
    await user.click(anchor);
    expect(screen.getByRole("dialog", { name: "Applied this week" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(anchor).toHaveFocus();
  });

  it("closes on an outside click", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    await user.click(screen.getByRole("button", { name: "Applied this week" }));
    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("renders a title, text and an optional action", async () => {
    const { container } = render(
      <EmptyState title="Nothing needs you right now">
        New items appear after the next run.
      </EmptyState>,
    );
    expect(screen.getByRole("heading", { name: "Nothing needs you right now" })).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });
});

