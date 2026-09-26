import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "./Toast";

function Trigger({ onUndo, seconds }: { onUndo?: () => void; seconds?: number }) {
  const toast = useToast();
  return <button onClick={() => toast.show({ message: "Marked Ramp done.", onUndo, seconds })}>go</button>;
}

describe("Toast", () => {
  it("announces through a polite live region and offers Undo", () => {
    vi.useFakeTimers();
    const onUndo = vi.fn();
    render(
      <ToastProvider>
        <Trigger onUndo={onUndo} />
      </ToastProvider>,
    );
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    act(() => screen.getByText("go").click());
    expect(region).toHaveTextContent("Marked Ramp done.");
    act(() => screen.getByRole("button", { name: "Undo" }).click());
    expect(onUndo).toHaveBeenCalledOnce();
    expect(region).not.toHaveTextContent("Marked Ramp done.");
    vi.useRealTimers();
  });

  it("dismisses itself after the configured seconds (provider default 8)", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider defaultSeconds={8}>
        <Trigger />
      </ToastProvider>,
    );
    act(() => screen.getByText("go").click());
    act(() => vi.advanceTimersByTime(7900));
    expect(screen.getByRole("status")).toHaveTextContent("Marked Ramp done.");
    act(() => vi.advanceTimersByTime(200));
    expect(screen.getByRole("status")).not.toHaveTextContent("Marked Ramp done.");
    vi.useRealTimers();
  });

  it("a per-toast seconds overrides the default", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Trigger seconds={2} />
      </ToastProvider>,
    );
    act(() => screen.getByText("go").click());
    act(() => vi.advanceTimersByTime(2100));
    expect(screen.getByRole("status")).not.toHaveTextContent("Marked Ramp done.");
    vi.useRealTimers();
  });
});
