import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { ReactNode } from "react";
import { ToastProvider } from "../../kit/Toast";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../../test/apiMock";
import { renderWithProviders } from "../job-detail/testUtils";
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

describe("Pipeline tick + injection badge (REQ-104/109)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("unticked row renders unchecked; click POSTs selected:true; null counts as ticked", async () => {
    const api = mockApi({ "POST /api/jobs/select": { ids: ["j1"], selected: true } });
    renderWithProviders(col("pick").cell(job({ job_id: "j1", company: "Acme", selected: 0 })));
    const box = screen.getByRole("checkbox", { name: "Tick Acme for pipeline" });
    expect(box).not.toBeChecked();
    await userEvent.click(box);
    await waitFor(() => expect(api.callsTo("POST /api/jobs/select")).toHaveLength(1));
    expect(api.callsTo("POST /api/jobs/select")[0]!.body).toEqual({ ids: ["j1"], selected: true });
    cleanup();
    renderWithProviders(col("pick").cell(job({ job_id: "j2", company: "Beta", selected: null })));
    expect(screen.getByRole("checkbox", { name: "Tick Beta for pipeline" })).toBeChecked();
  });

  it("follows server state after a click (no sticky local state); failed POST toasts", async () => {
    mockApi({ "POST /api/jobs/select": { status: 500, body: { detail: "disk full" } } });
    const ui = (selected: number) => col("pick").cell(job({ job_id: "j1", company: "Acme", selected }));
    const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}><ToastProvider>{children}</ToastProvider></QueryClientProvider>
    );
    const { rerender } = render(ui(1), { wrapper });
    await userEvent.click(screen.getByRole("checkbox", { name: "Tick Acme for pipeline" }));
    expect(await screen.findByText(/disk full/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Tick Acme for pipeline" })).toBeChecked();
    rerender(ui(0));
    expect(screen.getByRole("checkbox", { name: "Tick Acme for pipeline" })).not.toBeChecked();
  });

  it("keeps the new tick until the jobs list has refetched (no flash back to stale)", async () => {
    let release!: () => void;
    let selected = 0;
    const api = mockApi({
      "GET /api/jobs": () =>
        selected ? new Promise((r) => (release = () => r({ items: [job({ job_id: "j1", company: "Acme", selected })] }))) : { items: [job({ job_id: "j1", company: "Acme", selected })] },
      "POST /api/jobs/select": () => ((selected = 1), { ids: ["j1"], selected: true }),
    });
    function Row() {
      const q = useQuery({ queryKey: ["jobs"], queryFn: () => apiFetch<{ items: ReturnType<typeof job>[] }>("/api/jobs") });
      return q.data ? <>{col("pick").cell(q.data.items[0]!)}</> : null;
    }
    renderWithProviders(<Row />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Tick Acme for pipeline" }));
    await waitFor(() => expect(api.callsTo("GET /api/jobs")).toHaveLength(2));
    expect(screen.getByRole("checkbox", { name: "Tick Acme for pipeline" })).toBeChecked();
    release();
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Tick Acme for pipeline" })).toBeChecked());
  });

  it("flagged row shows the injection reasons to screen readers", () => {
    renderCell("company", job({ job_id: "j1", company: "Acme", injection: "hidden text" }));
    expect(screen.getByText("Possible prompt injection: hidden text")).toBeInTheDocument();
  });
});
