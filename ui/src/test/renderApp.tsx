import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";
import { routes } from "../app/routes";
import { ToastProvider } from "../kit/Toast";
import { FakeEventSource } from "./fakeEventSource";

/** Render the whole app (shell + routes) at `path` with a fresh query cache. Mock fetch first (apiMock). */
export function renderApp(path: string) {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...utils, router, qc };
}
