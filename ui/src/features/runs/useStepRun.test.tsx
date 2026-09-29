import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { useStepRun } from "./useStepRun";

afterEach(() => vi.unstubAllGlobals());

it("drops the run once its detail keeps failing, so the button is not stuck", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 500 })));
  const qc = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  qc.setQueryData(["stepRun", "scout", ""], "r-1");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useStepRun("scout"), { wrapper });
  expect(result.current.running).toBe(true);
  await waitFor(() => expect(result.current.running).toBe(false), { timeout: 4000 });
});
