import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { COLUMNS } from "./cells";
import { job } from "./fixtures";

function col(key: string) {
  const c = COLUMNS.find((c) => c.key === key);
  if (!c) throw new Error(`no column ${key}`);
  return c;
}

function renderCell(key: string, j = job({ job_id: "j1" })) {
  render(<MemoryRouter>{col(key).cell(j)}</MemoryRouter>);
}

describe("header filter columns (Codex #1)", () => {
  it("category: filterable, humanized", () => {
    const c = col("category");
    expect(c.filter).toBe("category");
    renderCell("category", job({ job_id: "j1", category: "swe" }));
    expect(screen.getByText("Swe")).toBeInTheDocument();
  });

  it("category: falls back to Empty when missing", () => {
    renderCell("category", job({ job_id: "j1", category: null }));
    expect(screen.getByText("No category")).toBeInTheDocument();
  });

  it("qa_passed: filterable, shows Passed/Failed", () => {
    const c = col("qa_passed");
    expect(c.filter).toBe("qa_passed");
    renderCell("qa_passed", job({ job_id: "j1", qa_passed: 1 }));
    expect(screen.getByText("Passed")).toBeInTheDocument();
  });

  it("qa_passed: shows Failed for 0, Empty for null", () => {
    renderCell("qa_passed", job({ job_id: "j1", qa_passed: 0 }));
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("closes_at: filterable, formatted date", () => {
    const c = col("closes_at");
    expect(c.filter).toBe("closes_at");
    renderCell("closes_at", job({ job_id: "j1", closes_at: "2026-10-01T00:00:00" }));
    expect(screen.getByText("Oct 1")).toBeInTheDocument();
  });

  it("closes_at: falls back to Empty when missing", () => {
    renderCell("closes_at", job({ job_id: "j1", closes_at: null }));
    expect(screen.getByText("No closing date")).toBeInTheDocument();
  });
});
