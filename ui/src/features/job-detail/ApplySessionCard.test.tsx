import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../../test/axe";
import { ApplySessionCard } from "./ApplySessionCard";
import { detail } from "./fixtures";
import { renderWithProviders } from "./testUtils";

const d = detail();

describe("ApplySessionCard", () => {
  it("lists steps with spoken done/stopped state and the outcome", () => {
    renderWithProviders(<ApplySessionCard jobId="nw01" session={d.apply_session} screenshots={d.screenshots} />);
    const card = screen.getByRole("region", { name: "Apply session" });
    const steps = within(card).getAllByRole("listitem").filter((li) => li.textContent?.match(/^\d\d/));
    expect(steps.map((s) => s.textContent)).toEqual([
      "01Done: Opened form",
      "02Done: Uploaded resume.pdf · 1 file",
      "03Stopped: Stopped before submit (Tier A)",
    ]);
    expect(within(card).getByText("Needs review")).toHaveAttribute("data-tone", "orange");
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
