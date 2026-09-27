import type { RouteObject } from "react-router";
import { NotFoundPage } from "../features/placeholder/PlaceholderPage";
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
      { path: "inbox", lazy: () => import("../features/inbox/InboxPage").then((m) => ({ Component: m.InboxPage })) },
      { path: "inbox/:jobId", lazy: () => import("../features/inbox/InboxPage").then((m) => ({ Component: m.InboxPage })) },
      { path: "contacts", lazy: () => import("../features/contacts/ContactsPage").then((m) => ({ Component: m.ContactsPage })) },
      { path: "runs", lazy: () => import("../features/runs/RunsPage").then((m) => ({ Component: m.RunsPage })) },
      { path: "runs/:runId", lazy: () => import("../features/runs/RunDetailPage").then((m) => ({ Component: m.RunDetailPage })) },
      { path: "settings/:section?", lazy: () => import("../features/settings/SettingsPage").then((m) => ({ Component: m.SettingsPage })) },
      { path: "kit", lazy: () => import("../features/kit/KitPage").then((m) => ({ Component: m.KitPage })) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
