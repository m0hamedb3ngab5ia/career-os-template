import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../test/axe";
import {
  ActionTypeLabel,
  Chip,
  NeedsLabel,
  PriorityChip,
  SafetyChip,
  StatusChip,
  StopReasonChip,
  TierBadge,
} from "./chips";

describe("chips", () => {
  it("StatusChip shows the label and tone", () => {
    render(<StatusChip status="needs_review" />);
    const chip = screen.getByText("Needs review");
    expect(chip).toHaveAttribute("data-tone", "orange");
  });

  it("unknown codes fall back to a gray, humanized chip", () => {
    render(<StatusChip status="on_hold" />);
    expect(screen.getByText("On hold")).toHaveAttribute("data-tone", "gray");
  });

  it("SafetyChip carries a dot and a label, never colour alone", () => {
    const { container } = render(<SafetyChip verdict="block" />);
    expect(screen.getByText("Block")).toHaveAttribute("data-tone", "red");
    expect(container.querySelector("[data-dot]")).not.toBeNull();
  });

  it("TierBadge announces the tier and shows a dash when there is none", () => {
    const { rerender } = render(<TierBadge tier="A" />);
    expect(screen.getByText("Tier", { exact: false })).toHaveClass("sr-only");
    expect(screen.getByText("A").closest("[data-tone]")).toHaveAttribute("data-tone", "purple");
    rerender(<TierBadge tier={null} />);
    expect(screen.getByText("No tier")).toBeInTheDocument();
  });

  it("PriorityChip, StopReasonChip, NeedsLabel, ActionTypeLabel use their tables", () => {
    render(
      <>
        <PriorityChip priority="H" />
        <StopReasonChip reason="auth_required" />
        <NeedsLabel needs="phone" />
        <ActionTypeLabel type="scam_suspected" />
      </>,
    );
    expect(screen.getByText("High")).toHaveAttribute("data-tone", "red");
    expect(screen.getByText("Login needed")).toHaveAttribute("data-tone", "orange");
    expect(screen.getByText("Phone")).toBeInTheDocument();
    expect(screen.getByText("Possible scam")).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <div>
        <Chip tone="blue">Queued</Chip>
        <SafetyChip verdict="pass" />
        <TierBadge tier="B" />
      </div>,
    );
    expect(await axeViolations(container)).toEqual([]);
  });
});
