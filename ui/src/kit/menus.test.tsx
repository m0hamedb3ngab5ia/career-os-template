import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { axeViolations } from "../test/axe";
import { TextField } from "./FormField";
import { Listbox } from "./Listbox";
import { Menu } from "./Menu";
import { Sheet } from "./Sheet";

const OPTS = [
  { value: "due", label: "Due date" },
  { value: "priority", label: "Priority" },
  { value: "needs", label: "Needs" },
];

function ControlledListbox({ onChange = () => {} }: { onChange?: (v: string) => void }) {
  const [v, setV] = useState("due");
  return (
    <Listbox
      label="Group by"
      value={v}
      options={OPTS}
      onValueChange={(x) => {
        setV(x);
        onChange(x);
      }}
    />
  );
}

describe("Listbox", () => {
  it("names the button with its caption and value, and picks by keyboard", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ControlledListbox onChange={onChange} />);
    const btn = screen.getByRole("button", { name: "Group by Due date" });
    expect(btn).toHaveAttribute("aria-haspopup", "listbox");
    btn.focus();
    await user.keyboard("{ArrowDown}");
    const list = screen.getByRole("listbox", { name: "Group by" });
    expect(list).toHaveFocus();
    expect(screen.getByRole("option", { name: "Due date" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onChange).toHaveBeenCalledWith("priority");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("button", { name: "Group by Priority" })).toHaveFocus();
  });

  it("Escape closes and returns focus; click picks", async () => {
    const user = userEvent.setup();
    render(<ControlledListbox />);
    await user.click(screen.getByRole("button", { name: /Group by/ }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("button", { name: /Group by/ })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: /Group by/ }));
    await user.click(screen.getByRole("option", { name: "Needs" }));
    expect(screen.getByRole("button", { name: "Group by Needs" })).toBeInTheDocument();
  });

  it("inline label reads 'Tier: All' and has no axe violations when open", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <Listbox label="Tier" labelPlacement="inline" value="" options={[{ value: "", label: "All" }]} onValueChange={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Tier: All" })).toBeInTheDocument();
    await user.click(screen.getByRole("button"));
    expect(await axeViolations(container)).toEqual([]);
  }, 20_000);
});

describe("Menu", () => {
  it("opens on ArrowDown with focus on the first enabled item; arrows skip disabled ones", async () => {
    const user = userEvent.setup();
    const a = vi.fn();
    const c = vi.fn();
    render(
      <Menu label="Move Acme to" items={[
        { key: "a", label: "Found", disabled: true, onSelect: vi.fn() },
        { key: "b", label: "Queued", onSelect: a },
        { key: "c", label: "Applied", onSelect: c },
      ]}>
        Move to…
      </Menu>,
    );
    screen.getByRole("button", { name: "Move to…" }).focus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menu", { name: "Move Acme to" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Queued" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Applied" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Queued" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(a).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("Escape closes and returns focus; disabled items do nothing", async () => {
    const user = userEvent.setup();
    const d = vi.fn();
    render(
      <Menu label="m" items={[{ key: "a", label: "Here", disabled: true, onSelect: d }, { key: "b", label: "There", onSelect: vi.fn() }]}>
        Move to…
      </Menu>,
    );
    await user.click(screen.getByRole("button", { name: "Move to…" }));
    await user.click(screen.getByRole("menuitem", { name: "Here" }));
    expect(d).not.toHaveBeenCalled();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByRole("button", { name: "Move to…" })).toHaveFocus();
  });
});

describe("Sheet", () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Add date
        </button>
        {open ? (
          <Sheet title="Add a date" description="When is it due?" onClose={() => setOpen(false)}
            footer={<button type="button" onClick={() => setOpen(false)}>Save</button>}>
            <TextField label="Due" type="date" defaultValue="" />
          </Sheet>
        ) : null}
      </>
    );
  }

  it("focuses the first field, traps Tab, closes on Escape and returns focus", async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Add date" }));
    const dialog = screen.getByRole("dialog", { name: "Add a date" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByLabelText("Due")).toHaveFocus();
    expect(await axeViolations(container)).toEqual([]);
    await user.tab();
    expect(screen.getByRole("button", { name: "Save" })).toHaveFocus();
    await user.tab();
    expect(screen.getByLabelText("Due")).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Add date" })).toHaveFocus();
  }, 20_000);
});
