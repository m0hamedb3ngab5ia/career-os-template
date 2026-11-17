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
      { path: "profile", lazy: () => import("../features/profile/ProfilePage").then((m) => ({ Component: m.ProfilePage })) },
      { path: "settings", lazy: () => import("../features/profile/SettingsPage").then((m) => ({ Component: m.SettingsPage })) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
