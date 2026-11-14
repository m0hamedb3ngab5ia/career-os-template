import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { axeViolations } from "../test/axe";
import { Menu } from "./Menu";

function Demo({ onPick = () => undefined }: { onPick?: (v: string) => void }) {
  const [cols, setCols] = useState({ ats: true, qa: false });
  return (
    <>
      <Menu label="Set status">
        <Menu.Trigger>Set status</Menu.Trigger>
        <Menu.Content>
          <Menu.RadioItem checked={false} onSelect={() => onPick("queued")}>Queued</Menu.RadioItem>
          <Menu.RadioItem checked onSelect={() => onPick("applied")}>Applied</Menu.RadioItem>
          <Menu.RadioItem checked={false} onSelect={() => onPick("offer")}>Offer</Menu.RadioItem>
        </Menu.Content>
      </Menu>
      <Menu label="Columns">
        <Menu.Trigger>Columns</Menu.Trigger>
        <Menu.Content>
          <Menu.CheckboxItem checked={cols.ats} onCheckedChange={(v) => setCols((c) => ({ ...c, ats: v }))}>
            ATS
          </Menu.CheckboxItem>
          <Menu.CheckboxItem checked={cols.qa} onCheckedChange={(v) => setCols((c) => ({ ...c, qa: v }))}>
            QA
          </Menu.CheckboxItem>
        </Menu.Content>
      </Menu>
    </>
  );
}

describe("Menu", () => {
  it("opens from the keyboard on the checked item, arrows move, Enter picks and closes back to the trigger", async () => {
    const user = userEvent.setup();
    const onPick = vi.fn();
    render(<Demo onPick={onPick} />);
    const trigger = screen.getByRole("button", { name: "Set status" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    trigger.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("menu", { name: "Set status" })).toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("menuitemradio", { name: "Applied" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitemradio", { name: "Offer" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitemradio", { name: "Queued" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("menuitemradio", { name: "Offer" })).toHaveFocus();
    await user.keyboard("{Home}{Enter}");
    expect(onPick).toHaveBeenCalledWith("queued");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("Escape closes and returns focus; outside click closes", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    const trigger = screen.getByRole("button", { name: "Set status" });
    await user.click(trigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    await user.click(trigger);
    await user.click(document.body);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("checkbox items toggle and keep the menu open", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    await user.click(screen.getByRole("button", { name: "Columns" }));
    const qa = screen.getByRole("menuitemcheckbox", { name: "QA" });
    expect(qa).toHaveAttribute("aria-checked", "false");
    await user.click(qa);
    expect(screen.getByRole("menuitemcheckbox", { name: "QA" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("menu", { name: "Columns" })).toBeInTheDocument();
    await user.keyboard(" ");
    expect(screen.getByRole("menuitemcheckbox", { name: "QA" })).toHaveAttribute("aria-checked", "false");
  });

  it("has no axe violations when open", async () => {
    const user = userEvent.setup();
    const { container } = render(<Demo />);
    await user.click(screen.getByRole("button", { name: "Columns" }));
    expect(await axeViolations(container)).toEqual([]);
  });
});
