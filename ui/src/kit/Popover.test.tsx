import { render, screen } from "@testing-library/react";
import { useRef } from "react";
import { describe, expect, it } from "vitest";
import { Popover } from "./Popover";

describe("Popover id", () => {
  it("takes an id so its anchor can point at it with aria-controls", () => {
    function Demo() {
      const anchor = useRef<HTMLButtonElement>(null);
      return (
        <>
          <button ref={anchor} aria-expanded aria-controls="stat-pop">
            Tile
          </button>
          <Popover id="stat-pop" open onClose={() => {}} anchorRef={anchor} label="Tile details">
            <p>Rows</p>
          </Popover>
        </>
      );
    }
    render(<Demo />);
    expect(screen.getByRole("dialog", { name: "Tile details" })).toHaveAttribute("id", "stat-pop");
  });
});
