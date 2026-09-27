import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LogPane, type LogLine } from "./LogPane";
import { fakeLayout } from "./testUtils";

const lines = (from: number, n: number): LogLine[] =>
  Array.from({ length: n }, (_, i) => ({ key: from + i, text: `line ${from + i}` }));

let restore: () => void;
let scrolls: ReturnType<typeof vi.fn>;
beforeEach(() => {
  restore = fakeLayout();
  scrolls = vi.fn();
  HTMLElement.prototype.scrollTo = scrolls as unknown as typeof HTMLElement.prototype.scrollTo;
});
afterEach(() => restore());

describe("LogPane", () => {
  it("keeps following the tail once the buffer is full (same length, new last line)", () => {
    const { rerender, getByRole } = render(<LogPane label="Live run output" lines={lines(1, 50)} empty="—" />);
    expect(getByRole("log", { name: "Live run output" })).toBeInTheDocument();
    const before = scrolls.mock.calls.length;
    rerender(<LogPane label="Live run output" lines={lines(2, 50)} empty="—" />);
    expect(scrolls.mock.calls.length).toBeGreaterThan(before);
  });

  it("shows the empty text with no lines", () => {
    const { getByText } = render(<LogPane label="Run log" lines={[]} empty="Nothing logged." />);
    expect(getByText("Nothing logged.")).toBeInTheDocument();
  });
});
