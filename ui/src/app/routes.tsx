import type { RouteObject } from "react-router";
import { NotFoundPage, PlaceholderPage } from "../features/placeholder/PlaceholderPage";
import { TodayPage } from "../features/today/TodayPage";
import { AppShell } from "./AppShell";

// Screens land slice by slice (docs/UI.md). Paths follow the mockup's links between artboards.
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <TodayPage /> },
      { path: "pipeline", element: <PlaceholderPage title="Pipeline" /> },
      { path: "jobs", lazy: () => import("../features/jobs/JobsPage").then((m) => ({ Component: m.JobsPage })) },
      { path: "jobs/:jobId", lazy: () => import("../features/job-detail/JobDetailPage").then((m) => ({ Component: m.JobDetailPage })) },
      { path: "actions", element: <PlaceholderPage title="Action Items" /> },
      { path: "inbox", element: <PlaceholderPage title="Inbox & Follow-ups" /> },
      { path: "inbox/:jobId", element: <PlaceholderPage title="Inbox & Follow-ups" /> },
      { path: "contacts", element: <PlaceholderPage title="Contacts" /> },
      { path: "runs", element: <PlaceholderPage title="Runs" /> },
      { path: "settings", element: <PlaceholderPage title="Settings" /> },
      { path: "settings/:section", element: <PlaceholderPage title="Settings" /> },
      { path: "kit", lazy: () => import("../features/kit/KitPage").then((m) => ({ Component: m.KitPage })) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
