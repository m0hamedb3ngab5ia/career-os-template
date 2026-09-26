import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../test/axe";
import { Button } from "./Button";
import { Dialog, Sheet } from "./Dialog";

function Demo({ kind }: { kind: "dialog" | "sheet" }) {
  const [open, setOpen] = useState(false);
  const Frame = kind === "dialog" ? Dialog : Sheet;
  return (
    <>
      <Button onClick={() => setOpen(true)}>Evidence</Button>
      <Frame open={open} onClose={() => setOpen(false)} title="Evidence for old posting" description="Links the check used.">
        <a href="https://example.com/a">First link</a>
        <button type="button">Second</button>
      </Frame>
    </>
  );
}

describe.each(["dialog", "sheet"] as const)("%s", (kind) => {
  it("opens as a labelled modal dialog, traps Tab, and Escape returns focus to the opener", async () => {
    const user = userEvent.setup();
    render(<Demo kind={kind} />);
    const opener = screen.getByRole("button", { name: "Evidence" });
    await user.click(opener);
    const dlg = screen.getByRole("dialog", { name: "Evidence for old posting" });
    expect(dlg).toHaveAttribute("aria-modal", "true");
    expect(dlg).toHaveAccessibleDescription("Links the check used.");
    // focus starts inside; Tab cycles within the dialog
    expect(dlg.contains(document.activeElement)).toBe(true);
    for (let i = 0; i < 5; i++) {
      await user.tab();
      expect(dlg.contains(document.activeElement)).toBe(true);
    }
    await user.tab({ shift: true });
    expect(dlg.contains(document.activeElement)).toBe(true);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("the Close button closes it", async () => {
    const user = userEvent.setup();
    render(<Demo kind={kind} />);
    await user.click(screen.getByRole("button", { name: "Evidence" }));
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("has no axe violations", { timeout: 20_000 }, async () => {
    const user = userEvent.setup();
    render(<Demo kind={kind} />);
    await user.click(screen.getByRole("button", { name: "Evidence" }));
    expect(await axeViolations(document.body)).toEqual([]);
  });
});
