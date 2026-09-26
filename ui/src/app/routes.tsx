import type { RouteObject } from "react-router";
import { NotFoundPage, PlaceholderPage } from "../features/placeholder/PlaceholderPage";
import { AppShell } from "./AppShell";

// Screens land slice by slice (docs/UI.md). Paths follow the mockup's links between artboards.
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <PlaceholderPage title="Today" /> },
      { path: "pipeline", element: <PlaceholderPage title="Pipeline" /> },
      { path: "jobs", element: <PlaceholderPage title="Jobs" /> },
      { path: "jobs/:jobId", element: <PlaceholderPage title="Job detail" /> },
      { path: "actions", element: <PlaceholderPage title="Action Items" /> },
      { path: "inbox", lazy: () => import("../features/inbox/InboxPage").then((m) => ({ Component: m.InboxPage })) },
      { path: "inbox/:jobId", lazy: () => import("../features/inbox/InboxPage").then((m) => ({ Component: m.InboxPage })) },
      { path: "contacts", lazy: () => import("../features/contacts/ContactsPage").then((m) => ({ Component: m.ContactsPage })) },
      { path: "runs", element: <PlaceholderPage title="Runs" /> },
      { path: "settings", element: <PlaceholderPage title="Settings" /> },
      { path: "settings/:section", element: <PlaceholderPage title="Settings" /> },
      { path: "kit", lazy: () => import("../features/kit/KitPage").then((m) => ({ Component: m.KitPage })) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
