import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../../test/axe";
import { ApplySessionCard } from "./ApplySessionCard";
import { detail } from "./fixtures";
import { renderWithProviders } from "./testUtils";

const d = detail();

describe("ApplySessionCard", () => {
  it("one short check line per step, raw detail behind a click, and the outcome", () => {
    renderWithProviders(<ApplySessionCard jobId="nw01" session={d.apply_session} screenshots={d.screenshots} />);
    const card = screen.getByRole("region", { name: "Apply session" });
    const steps = within(card).getAllByRole("listitem").filter((li) => li.dataset.step);
    expect(steps.map((s) => s.firstChild?.textContent)).toEqual([
      "✓ Done: Opened form",
      "✓ Done: Uploaded resume.pdf",
      "✗ Stopped: Stopped before submit (Tier A)",
    ]);
    const note = within(steps[1]!).getByText("1 file");
    expect(note.closest("details")).not.toHaveAttribute("open");
    expect(within(card).getByText("Needs review")).toHaveAttribute("data-tone", "orange");
  });

  it("lists fields left as a checklist of remaining questions", () => {
    renderWithProviders(
      <ApplySessionCard jobId="nw01" session={d.apply_session} screenshots={[]} fieldsLeft={["Visa status", "Start date"]} />,
    );
    const list = screen.getByRole("list", { name: "Questions left for you" });
    expect(within(list).getAllByRole("checkbox").map((c) => c.closest("label")?.textContent?.trim())).toEqual(["Visa status", "Start date"]);
  });

  it("thumbnails have alt text, a size and lazy loading", () => {
    renderWithProviders(<ApplySessionCard jobId="nw01" session={d.apply_session} screenshots={d.screenshots} />);
    const img = screen.getByAltText("Screenshot 1: 01 form");
    expect(img).toHaveAttribute("src", "/api/jobs/nw01/files/screenshots/01_form.png");
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("width", "120");
    expect(img).toHaveAttribute("height", "72");
  });

  it("the viewer opens from the keyboard, arrows move, Escape returns focus to the thumbnail", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ApplySessionCard jobId="nw01" session={d.apply_session} screenshots={d.screenshots} />);
    const thumb = screen.getByRole("button", { name: "Open screenshot 2 of 2: 02 review" });
    thumb.focus();
    await user.keyboard("{Enter}");
    let dlg = screen.getByRole("dialog", { name: "Screenshot 2 of 2" });
    expect(within(dlg).getByRole("img")).toHaveAttribute("src", "/api/jobs/nw01/files/screenshots/02_review.png");
    await user.keyboard("{ArrowRight}");
    dlg = screen.getByRole("dialog", { name: "Screenshot 1 of 2" });
    await user.click(within(dlg).getByRole("button", { name: "Previous" }));
    expect(screen.getByRole("dialog", { name: "Screenshot 2 of 2" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(thumb).toHaveFocus();
  });

  it("empty state without a session", () => {
    renderWithProviders(<ApplySessionCard jobId="nw01" session={null} screenshots={[]} />);
    expect(screen.getByText(/No apply session yet/)).toBeInTheDocument();
  });

  it("has no axe violations (card and open viewer)", { timeout: 20_000 }, async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(
      <ApplySessionCard jobId="nw01" session={d.apply_session} screenshots={d.screenshots} />,
    );
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: /Open screenshot 1/ }));
    expect(await axeViolations(document.body)).toEqual([]);
  });
});
