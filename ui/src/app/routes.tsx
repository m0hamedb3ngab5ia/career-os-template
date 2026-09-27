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
      { path: "pipeline", lazy: () => import("../features/pipeline/PipelinePage").then((m) => ({ Component: m.PipelinePage })) },
      { path: "jobs", lazy: () => import("../features/jobs/JobsPage").then((m) => ({ Component: m.JobsPage })) },
      { path: "jobs/:jobId", lazy: () => import("../features/job-detail/JobDetailPage").then((m) => ({ Component: m.JobDetailPage })) },
      { path: "actions", lazy: () => import("../features/actions/ActionItemsPage").then((m) => ({ Component: m.ActionItemsPage })) },
      { path: "inbox", element: <PlaceholderPage title="Inbox & Follow-ups" /> },
      { path: "inbox/:jobId", element: <PlaceholderPage title="Inbox & Follow-ups" /> },
      { path: "contacts", element: <PlaceholderPage title="Contacts" /> },
      { path: "runs", lazy: () => import("../features/runs/RunsPage").then((m) => ({ Component: m.RunsPage })) },
      { path: "runs/:runId", lazy: () => import("../features/runs/RunDetailPage").then((m) => ({ Component: m.RunDetailPage })) },
      { path: "settings/:section?", lazy: () => import("../features/settings/SettingsPage").then((m) => ({ Component: m.SettingsPage })) },
      { path: "kit", lazy: () => import("../features/kit/KitPage").then((m) => ({ Component: m.KitPage })) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
