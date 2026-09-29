import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../test/axe";
import { Details } from "./Details";

describe("Details", () => {
  it("is collapsed by default, named by its summary, and opens on click", async () => {
    const { container } = render(
      <Details summary="Advanced">
        <p>run-123</p>
      </Details>,
    );
    const toggle = screen.getByText("Advanced");
    expect(container.querySelector("details")).not.toHaveAttribute("open");
    await userEvent.click(toggle);
    expect(container.querySelector("details")).toHaveAttribute("open");
    expect(screen.getByText("run-123")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("can start open", () => {
    const { container } = render(<Details summary="Logs" defaultOpen>x</Details>);
    expect(container.querySelector("details")).toHaveAttribute("open");
  });
});
