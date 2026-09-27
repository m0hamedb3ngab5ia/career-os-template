import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LOG_ANNOUNCE_MS, LogPane, type LogLine } from "./LogPane";
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

  it("does not read every line aloud: the log itself is not a live region", () => {
    render(<LogPane label="Live run output" lines={lines(1, 3)} empty="—" live />);
    expect(screen.getByRole("log", { name: "Live run output" })).toHaveAttribute("aria-live", "off");
  });

  it("summarises new lines in a status at most every few seconds while live", () => {
    vi.useFakeTimers();
    try {
      const { rerender } = render(<LogPane label="Live run output" lines={lines(1, 1)} empty="—" live />);
      const status = screen.getByTestId("log-announcer");
      expect(status).toHaveAttribute("role", "status");
      // The first burst is announced at once, as a count.
      rerender(<LogPane label="Live run output" lines={lines(1, 3)} empty="—" live />);
      expect(status).toHaveTextContent("2 new log lines");
      // More lines within the window wait for it to pass, then come as one summary.
      rerender(<LogPane label="Live run output" lines={lines(1, 4)} empty="—" live />);
      const withError = [...lines(1, 5), { key: 6, text: "boom", error: true }];
      rerender(<LogPane label="Live run output" lines={withError} empty="—" live />);
      expect(status).toHaveTextContent("2 new log lines");
      act(() => vi.advanceTimersByTime(LOG_ANNOUNCE_MS));
      expect(status).toHaveTextContent("3 new log lines, 1 error");
    } finally {
      vi.useRealTimers();
    }
  });

  it("re-reads an identical summary and stays quiet when the last seen line left the buffer", () => {
    vi.useFakeTimers();
    try {
      const { rerender } = render(<LogPane label="Live run output" lines={lines(1, 1)} empty="—" live />);
      const status = screen.getByTestId("log-announcer");
      rerender(<LogPane label="Live run output" lines={lines(1, 3)} empty="—" live />);
      const first = status.textContent;
      act(() => vi.advanceTimersByTime(LOG_ANNOUNCE_MS));
      rerender(<LogPane label="Live run output" lines={lines(1, 5)} empty="—" live />);
      expect(status).toHaveTextContent("2 new log lines");
      expect(status.textContent).not.toBe(first);
      // Line 5 is gone from a buffer of 100 fresh lines: the count is unknown, so nothing new is said.
      act(() => vi.advanceTimersByTime(LOG_ANNOUNCE_MS));
      const before = status.textContent;
      rerender(<LogPane label="Live run output" lines={lines(200, 100)} empty="—" live />);
      act(() => vi.advanceTimersByTime(LOG_ANNOUNCE_MS));
      expect(status.textContent).toBe(before);
    } finally {
      vi.useRealTimers();
    }
  });

  it("announces nothing for a finished run's log", () => {
    const { rerender } = render(<LogPane label="Run log" lines={lines(1, 1)} empty="—" />);
    rerender(<LogPane label="Run log" lines={lines(1, 5)} empty="—" />);
    expect(screen.getByTestId("log-announcer")).toHaveTextContent("");
  });
});
