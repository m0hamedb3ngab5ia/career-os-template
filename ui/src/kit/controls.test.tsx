import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { axeViolations } from "../test/axe";
import { Button } from "./Button";
import { ConfirmPanel } from "./ConfirmPanel";
import { EmptyState } from "./EmptyState";
import { ExternalLink } from "./ExternalLink";
import { MarkDoneCircle } from "./MarkDoneCircle";
import { Popover } from "./Popover";
import { SegmentedControl } from "./SegmentedControl";
import { Switch } from "./Switch";

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

describe("Switch", () => {
  it("names the setting, toggles by click and keyboard", async () => {
    const user = userEvent.setup();
    function Demo() {
      const [on, setOn] = useState(false);
      return <Switch checked={on} onCheckedChange={setOn} label="Scout schedule" />;
    }
    render(<Demo />);
    const sw = screen.getByRole("switch", { name: "Scout schedule" });
    expect(sw).toHaveAttribute("aria-checked", "false");
    await user.click(sw);
    expect(sw).toHaveAttribute("aria-checked", "true");
    sw.focus();
    await user.keyboard(" ");
    expect(sw).toHaveAttribute("aria-checked", "false");
    await user.click(screen.getByText("Scout schedule"));
    expect(sw).toHaveAttribute("aria-checked", "true");
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

describe("ConfirmPanel", () => {
  it("is an alertdialog that focuses the safe choice; Escape cancels", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(
      <ConfirmPanel
        question="Withdraw from Acme? You can’t undo this."
        cancelLabel="Keep application"
        confirmLabel="Withdraw"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    );
    expect(screen.getByRole("alertdialog", { name: /Withdraw from Acme/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep application" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Withdraw" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});

describe("MarkDoneCircle", () => {
  it("is a checkbox named after the item", () => {
    const onChange = vi.fn();
    render(<MarkDoneCircle done={false} onDoneChange={onChange} itemName="Ramp LinkedIn note" />);
    const cb = screen.getByRole("checkbox", { name: "Mark Ramp LinkedIn note done" });
    expect(cb).toHaveAttribute("aria-checked", "false");
    fireEvent.click(cb);
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe("ExternalLink", () => {
  it("opens in a new tab safely and says so to screen readers", () => {
    render(<ExternalLink href="https://example.com/jobs/1">Open posting</ExternalLink>);
    const a = screen.getByRole("link", { name: /Open posting/ });
    expect(a).toHaveAttribute("target", "_blank");
    expect(a).toHaveAttribute("rel", "noopener noreferrer");
    expect(a).toHaveTextContent("opens in a new tab");
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

