import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../test/axe";
import { ConfirmPanel } from "./ConfirmPanel";
import { Meter } from "./Meter";

describe("Meter", () => {
  it("is a named progress bar whose value text matches what is shown", async () => {
    const { container } = render(<Meter label="Time budget" value={21} max={90} valueText="21 of 90 min" />);
    const bar = screen.getByRole("progressbar", { name: "Time budget" });
    expect(bar).toHaveAttribute("aria-valuenow", "21");
    expect(bar).toHaveAttribute("aria-valuemax", "90");
    expect(bar).toHaveAttribute("aria-valuetext", "21 of 90 min");
    expect(screen.getByText("21 of 90 min")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("clamps an overrun and survives a zero max", () => {
    const { rerender } = render(<Meter label="Jobs" value={7} max={5} valueText="7 of 5" note="over budget" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "5");
    expect(screen.getByText("7 of 5 · over budget")).toBeInTheDocument();
    rerender(<Meter label="Jobs" value={0} max={0} valueText="0 of 0" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  });
});

describe("ConfirmPanel variant", () => {
  it("uses a primary confirm for consequential, non-destructive actions", () => {
    render(
      <ConfirmPanel
        question="Install the scheduler?"
        cancelLabel="Not now"
        confirmLabel="Install"
        confirmVariant="primary"
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Install" })).toHaveAttribute("data-variant", "primary");
    expect(screen.getByRole("alertdialog")).toHaveAttribute("data-variant", "primary");
  });
});

describe("ConfirmPanel focus return", () => {
  function Demo() {
    const trigger = useRef<HTMLButtonElement>(null);
    const [open, setOpen] = useState(false);
    return (
      <>
        {open ? null : (
          <button ref={trigger} type="button" onClick={() => setOpen(true)}>
            Uninstall
          </button>
        )}
        {open ? (
          <ConfirmPanel
            question="Uninstall the scheduler?"
            cancelLabel="Keep it"
            confirmLabel="Uninstall"
            returnFocusRef={trigger}
            onCancel={() => setOpen(false)}
            onConfirm={() => setOpen(false)}
          />
        ) : null}
      </>
    );
  }

  it("hands focus back to the trigger on Escape, Cancel and after confirming", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    for (const close of ["{Escape}", "cancel", "confirm"] as const) {
      await user.click(screen.getByRole("button", { name: "Uninstall" }));
      expect(screen.getByRole("button", { name: "Keep it" })).toHaveFocus();
      if (close === "{Escape}") await user.keyboard(close);
      else await user.click(screen.getByRole("button", { name: close === "cancel" ? "Keep it" : "Uninstall" }));
      expect(screen.getByRole("button", { name: "Uninstall" })).toHaveFocus();
    }
  });
});
