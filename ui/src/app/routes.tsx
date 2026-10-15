import { redirect, type RouteObject } from "react-router";
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
      // DEC-022: the Pipeline page became Jobs › Applied › Board (REQ-129); the server also 308s /pipeline.
      { path: "pipeline", loader: () => redirect("/jobs?tab=applied&view=board") },
      { path: "pipeline/batch/:id", lazy: () => import("../features/pipeline/batch/Progress").then((m) => ({ Component: m.BatchProgressPage })) },
      { path: "jobs", lazy: () => import("../features/jobs/JobsPage").then((m) => ({ Component: m.JobsPage })) },
      { path: "jobs/:jobId", lazy: () => import("../features/jobs/JobsRoute").then((m) => ({ Component: m.JobsRoute })) },
      { path: "actions", lazy: () => import("../features/actions/ActionItemsPage").then((m) => ({ Component: m.ActionItemsPage })) },
      { path: "inbox", lazy: () => import("../features/inbox/InboxPage").then((m) => ({ Component: m.InboxPage })) },
      { path: "inbox/:jobId", lazy: () => import("../features/inbox/InboxPage").then((m) => ({ Component: m.InboxPage })) },
      { path: "contacts", lazy: () => import("../features/contacts/ContactsPage").then((m) => ({ Component: m.ContactsPage })) },
      { path: "automation", lazy: () => import("../features/runs/RunsPage").then((m) => ({ Component: m.RunsPage })) },
      { path: "automation/runs/:runId", lazy: () => import("../features/runs/RunDetailPage").then((m) => ({ Component: m.RunDetailPage })) },
      // Old Runs paths (design doc 2.1): kept as redirects so bookmarks and links still land.
      { path: "runs", loader: ({ request }) => redirect(`/automation${new URL(request.url).search}`) },
      { path: "runs/:runId", loader: ({ request, params }) => redirect(`/automation/runs/${encodeURIComponent(params.runId!)}${new URL(request.url).search}`) },
      { path: "profile", lazy: () => import("../features/profile/ProfilePage").then((m) => ({ Component: m.ProfilePage })) },
      { path: "profile/answers", lazy: () => import("../features/profile/AnswersPage").then((m) => ({ Component: m.AnswersPage })) },
      { path: "profile/resumes/:rid", lazy: () => import("../features/profile/ResumePage").then((m) => ({ Component: m.ResumePage })) },
      { path: "resumes/:rid", lazy: () => import("../features/workspace/WorkspacePage").then((m) => ({ Component: m.WorkspacePage })) },
      { path: "settings/:section?", lazy: () => import("../features/settings/SettingsPage").then((m) => ({ Component: m.SettingsPage })) },
      { path: "kit", lazy: () => import("../features/kit/KitPage").then((m) => ({ Component: m.KitPage })) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
