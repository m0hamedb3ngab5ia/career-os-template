import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { axeViolations } from "../test/axe";
import { Button } from "./Button";
import { Sheet } from "./Sheet";
import { UnavailableButton } from "./UnavailableButton";

function Demo({ onClose }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Open draft</Button>
      <Sheet
        open={open}
        onClose={() => {
          onClose?.();
          setOpen(false);
        }}
        title="LinkedIn draft"
        footer={<Button variant="primary">Approve</Button>}
      >
        <p>Letter text</p>
        <input aria-label="Mutuals" />
      </Sheet>
    </>
  );
}

describe("Sheet", () => {
  it("opens as a named modal dialog with focus inside, and has no axe violations", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    await user.click(screen.getByRole("button", { name: "Open draft" }));
    const dialog = screen.getByRole("dialog", { name: "LinkedIn draft" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(await axeViolations(document.body)).toEqual([]);
  });

  it("traps Tab inside and wraps both ways", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    await user.click(screen.getByRole("button", { name: "Open draft" }));
    const close = screen.getByRole("button", { name: "Close" });
    const approve = screen.getByRole("button", { name: "Approve" });
    expect(close).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("textbox", { name: "Mutuals" })).toHaveFocus();
    await user.tab();
    expect(approve).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(approve).toHaveFocus();
  });

  it("Escape closes and returns focus to the opener; Close does too", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Demo onClose={onClose} />);
    const opener = screen.getByRole("button", { name: "Open draft" });
    await user.click(opener);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
    await user.click(opener);
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(opener).toHaveFocus();
  });
});

describe("UnavailableButton", () => {
  it("is focusable, reads its reason, and does nothing", async () => {
    const user = userEvent.setup();
    const { container } = render(<UnavailableButton reason="Inbox sync isn't set up yet">Sync inbox</UnavailableButton>);
    const b = screen.getByRole("button", { name: "Sync inbox" });
    expect(b).toHaveAttribute("aria-disabled", "true");
    expect(b).toHaveAccessibleDescription("Inbox sync isn't set up yet");
    await user.tab();
    expect(b).toHaveFocus();
    await user.click(b);
    expect(await axeViolations(container)).toEqual([]);
  });
});
