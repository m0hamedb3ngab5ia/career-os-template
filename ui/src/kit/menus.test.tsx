import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Menu } from "./Menu";

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
