import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { ToastProvider } from "../../kit/Toast";
import { STATUSES, STOP_REASONS } from "../../kit/labels";
import { axeViolations } from "../../test/axe";
import { KitPage } from "./KitPage";

function renderKit() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <KitPage />
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("KitPage", () => {
  it("renders the kit once per theme", () => {
    renderKit();
    const light = screen.getByRole("region", { name: "Light" });
    const dark = screen.getByRole("region", { name: "Dark" });
    expect(light).toHaveAttribute("data-theme", "light");
    expect(dark).toHaveAttribute("data-theme", "dark");
    for (const board of [light, dark]) {
      for (const { label } of Object.values(STATUSES)) expect(within(board).getAllByText(label).length).toBeGreaterThan(0);
      for (const { label } of Object.values(STOP_REASONS)) expect(within(board).getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it("interactive demos work: toast with undo", async () => {
    const user = userEvent.setup();
    renderKit();
    const light = screen.getByRole("region", { name: "Light" });
    await user.click(within(light).getByRole("button", { name: "Show undo toast" }));
    expect(screen.getByRole("status")).toHaveTextContent("Marked Ramp done.");
  });

  it("has no axe violations", async () => {
    const { container } = renderKit();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("has no axe violations in the dark theme, board and page", async () => {
    document.documentElement.setAttribute("data-theme", "dark");
    try {
      renderKit();
      const dark = screen.getByRole("region", { name: "Dark" });
      expect(dark).toHaveAttribute("data-theme", "dark");
      expect(await axeViolations(dark)).toEqual([]);
      expect(await axeViolations(document.body)).toEqual([]);
    } finally {
      document.documentElement.removeAttribute("data-theme");
    }
  });

  it("shows an unavailable control with its reason and opens a sheet", async () => {
    const user = userEvent.setup();
    renderKit();
    const light = screen.getByRole("region", { name: "Light" });
    expect(within(light).getByRole("button", { name: "Sync" })).toHaveAccessibleDescription(
      "This needs a backend that isn't built yet",
    );
    await user.click(within(light).getByRole("button", { name: "Open sheet" }));
    expect(screen.getByRole("dialog", { name: "Add item" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(within(light).getByRole("button", { name: "Open sheet" })).toHaveFocus();
  });
});
