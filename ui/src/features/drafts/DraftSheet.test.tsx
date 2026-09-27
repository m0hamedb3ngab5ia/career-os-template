import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../kit/Toast";
import { axeViolations } from "../../test/axe";
import { DraftSheet } from "./DraftSheet";
import { draft, linkedinDraft } from "./fixtures";

type Props = Omit<ComponentProps<typeof DraftSheet>, "open" | "onClose">;

function Harness(props: Props) {
  const [open, setOpen] = useState(false);
  return (
    <ToastProvider>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <DraftSheet open={open} onClose={() => setOpen(false)} {...props} />
    </ToastProvider>
  );
}

async function openWith(props: Props) {
  const user = userEvent.setup();
  render(<Harness {...props} />);
  await user.click(screen.getByRole("button", { name: "Open" }));
  return { user, dialog: screen.getByRole("dialog") };
}

describe("DraftSheet", () => {
  it("shows the draft with placeholders marked, and Approve waits until they are filled", async () => {
    const { dialog } = await openWith({
      draft: draft(),
      company: "Hooli",
      jobTitle: "New Grad Engineer",
      tier: "B",
      approve: { onApprove: vi.fn() },
    });
    expect(dialog).toHaveAccessibleName("After-apply note");
    expect(within(dialog).getByText("2 placeholders")).toBeInTheDocument();
    const marks = dialog.querySelectorAll("mark");
    expect([...marks].map((m) => m.textContent)).toEqual(["[SPECIFIC CONNECTION]", "[MOST RELEVANT EXPERIENCE]"]);
    const approve = within(dialog).getByRole("button", { name: "Approve after-apply note" });
    expect(approve).toBeDisabled();
    expect(approve).toHaveAccessibleDescription("Fill 2 placeholders before approving");
    expect(within(dialog).getByText("Verified")).toBeInTheDocument();
    expect(await axeViolations(dialog)).toEqual([]);
  });

  it("Approve and Discard without a backend are off with a reason", async () => {
    const { dialog } = await openWith({
      draft: draft({ placeholders: [], body: "Hi Dana, all filled." }),
      approve: { unavailable: "Follow-up sending isn't built yet" },
      discard: { unavailable: "Discarding drafts isn't built yet" },
      edit: { unavailable: "Editing drafts here isn't built yet" },
    });
    const approve = within(dialog).getByRole("button", { name: "Approve after-apply note" });
    expect(approve).toHaveAttribute("aria-disabled", "true");
    expect(approve).toHaveAccessibleDescription("Follow-up sending isn't built yet");
    expect(within(dialog).getByRole("button", { name: "Discard draft" })).toHaveAccessibleDescription(
      "Discarding drafts isn't built yet",
    );
    expect(within(dialog).getByRole("button", { name: /Edit/ })).toHaveAttribute("aria-disabled", "true");
  });

  it("Discard asks first, then offers Undo", async () => {
    const onDiscard = vi.fn();
    const onUndo = vi.fn();
    const { user, dialog } = await openWith({ draft: draft(), discard: { onDiscard, onUndo } });
    await user.click(within(dialog).getByRole("button", { name: "Discard draft" }));
    const confirm = within(dialog).getByRole("alertdialog", { name: "Discard this draft?" });
    expect(within(confirm).getByRole("button", { name: "Keep draft" })).toHaveFocus();
    await user.click(within(confirm).getByRole("button", { name: "Discard" }));
    expect(onDiscard).toHaveBeenCalledOnce();
    await user.click(within(dialog).getByRole("button", { name: "Undo" }));
    expect(onUndo).toHaveBeenCalledOnce();
    expect(within(dialog).getByRole("button", { name: "Discard draft" })).toBeInTheDocument();
  });

  it("a LinkedIn draft is read-only: message and connection note, Copy text, no Approve", async () => {
    const { dialog } = await openWith({ draft: linkedinDraft() });
    expect(dialog).toHaveAccessibleName("LinkedIn draft");
    expect(within(dialog).getByText("LinkedIn · you send")).toBeInTheDocument();
    expect(within(dialog).getByRole("heading", { name: "Connection note" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /Approve/ })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Copy text" })).toBeInTheDocument();
  });

  it("pages through several drafts", async () => {
    const onNext = vi.fn();
    const { user, dialog } = await openWith({
      draft: linkedinDraft(),
      pager: { index: 0, count: 3, onPrev: vi.fn(), onNext },
    });
    expect(within(dialog).getByText("1 of 3")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Previous" })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: "Next" }));
    expect(onNext).toHaveBeenCalledOnce();
  });

  it("Escape closes it and focus goes back to the opener", async () => {
    const { user } = await openWith({ draft: draft() });
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Open" })).toHaveFocus();
  });
});
