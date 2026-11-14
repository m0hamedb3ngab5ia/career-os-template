import { redirect, type RouteObject } from "react-router";
import { NotFoundPage } from "./NotFoundPage";
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
      { path: "jobs", lazy: () => import("../features/jobs/JobsPage").then((m) => ({ Component: m.JobsPage })) },
      { path: "jobs/:jobId", lazy: () => import("../features/jobs/JobsRoute").then((m) => ({ Component: m.JobsRoute })) },
      { path: "profile", lazy: () => import("../features/profile/ProfilePage").then((m) => ({ Component: m.ProfilePage })) },
      { path: "profile/answers", lazy: () => import("../features/profile/AnswersPage").then((m) => ({ Component: m.AnswersPage })) },
      { path: "profile/resumes/:rid", lazy: () => import("../features/profile/ResumePage").then((m) => ({ Component: m.ResumePage })) },
      { path: "resumes/:rid", lazy: () => import("../features/workspace/WorkspacePage").then((m) => ({ Component: m.WorkspacePage })) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
