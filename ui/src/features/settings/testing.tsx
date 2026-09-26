// Test helpers for the Settings screens: a small, fictional schema in the server's shape, a routed fetch mock
// and a render wrapper (memory router + query client + toasts).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";
import { ToastProvider } from "../../kit/Toast";
import { SettingsPage } from "./SettingsPage";
import type { FieldSchema, SectionData } from "./types";

export function field(p: Partial<FieldSchema> & Pick<FieldSchema, "file" | "key" | "control" | "label">): FieldSchema {
  return {
    id: `${p.file}:${p.key}`,
    help: "",
    default: null,
    recommended: true,
    personal: false,
    options: [],
    strict_options: true,
    min: null,
    max: null,
    step: null,
    integer: false,
    nullable: false,
    unit: "",
    locked: false,
    readonly: false,
    note: "",
    ...p,
  };
}

export const SECTIONS = [
  { id: "general", title: "General", help: "", files: ["pipeline"] },
  { id: "autonomy", title: "Autonomy", help: "", files: ["pipeline", "targets"] },
  { id: "safety", title: "Safety", help: "", files: ["targets"] },
  { id: "runs", title: "Runs & schedule", help: "", files: ["pipeline"] },
  { id: "storage", title: "Storage & efficiency", help: "", files: ["pipeline"] },
];

function tier(letter: string, auto: boolean) {
  return {
    id: `tier_${letter.toLowerCase()}`,
    title: `Tier ${letter}`,
    help: "",
    items: [
      field({ file: "targets", key: `tiers.${letter}.description`, control: "text", label: "Description", default: `tier ${letter}` }),
      field({
        file: "targets",
        key: `tiers.${letter}.auto_submit`,
        control: "switch",
        label: "Auto-submit when you run Apply",
        default: auto,
        locked: letter === "A",
        note: letter === "A" ? "Tier A is never auto-submitted, whatever the file says." : "",
      }),
      field({
        file: "targets",
        key: `tiers.${letter}.cover_letter`,
        control: "select",
        label: "Cover letter",
        default: "always",
        options: ["always", "if_required"],
      }),
    ],
  };
}

export function autonomyData(): SectionData {
  const volume = field({
    file: "targets",
    key: "volume.max_applications_per_day",
    control: "number",
    label: "Applications per day",
    default: 15,
    min: 1,
    integer: true,
  });
  const cooldown = field({
    file: "targets",
    key: "volume.same_company_cooldown_days",
    control: "number",
    label: "Cooldown after a rejection",
    default: 30,
    unit: "days",
    integer: true,
  });
  const connected = field({
    file: "pipeline",
    key: "outreach.manual_if_connected",
    control: "switch",
    label: "Tailor by hand when you're already connected",
    default: true,
  });
  return {
    section: {
      id: "autonomy",
      title: "Autonomy",
      help: "",
      files: ["pipeline", "targets"],
      groups: [
        tier("A", false),
        tier("B", true),
        tier("C", true),
        { id: "volume", title: "Volume", help: "", items: [volume, cooldown] },
        {
          id: "outreach",
          title: "Outreach",
          help: "",
          items: [
            { control: "policy", label: "LinkedIn messages", value: "Draft only", why: "You send every message.", locked: true },
            connected,
          ],
        },
      ],
    },
    values: {
      "targets:tiers.A.description": "tier A",
      "targets:tiers.A.auto_submit": false,
      "targets:tiers.A.cover_letter": "always",
      "targets:tiers.B.description": "tier B",
      "targets:tiers.B.auto_submit": false,
      "targets:tiers.B.cover_letter": "always",
      "targets:tiers.C.description": "tier C",
      "targets:tiers.C.auto_submit": true,
      "targets:tiers.C.cover_letter": "if_required",
      "targets:volume.max_applications_per_day": 12,
      "targets:volume.same_company_cooldown_days": 30,
      "pipeline:outreach.manual_if_connected": true,
    },
    defaults: {},
    files: { pipeline: "config/pipeline.yaml", targets: "config/targets.yaml" },
    version: "v1",
  };
}

export function runsData(): SectionData {
  const f = (key: string, control: string, label: string, def: unknown, extra: Partial<FieldSchema> = {}) =>
    field({ file: "pipeline", key, control, label, default: def, ...extra });
  const presets = {
    small: { max_score_jobs: 10, max_prepare_jobs: 2, max_minutes: 30 },
    medium: { max_score_jobs: 25, max_prepare_jobs: 5, max_minutes: 90 },
  };
  const items = {
    budget: [
      f("runs.preset", "preset_cards", "Budget", "medium", { options: ["small", "medium", "custom"] }),
      f("runs.presets", "key_value", "Preset sizes", presets, { readonly: true, note: "Fixed sizes." }),
      f("runs.custom.max_score_jobs", "number", "Custom: jobs to score", 25, { integer: true }),
      f("runs.custom.max_prepare_jobs", "number", "Custom: jobs to prepare", 5, { integer: true }),
      f("runs.custom.max_minutes", "number", "Custom: time limit", 90, { integer: true }),
    ],
    ranking: [
      f("runs.ranking.freshness_weight", "slider", "Freshness", 60, { min: 0, max: 100, integer: true, unit: "points" }),
      f("runs.ranking.fresh_hours", "number", "Fresh for", 48, { integer: true, unit: "hours" }),
    ],
    auto: [
      f("runs.auto_submit.enabled", "switch", "Scheduled runs may submit", false, {
        readonly: true,
        note: "Runs never apply in this version.",
      }),
      f("runs.auto_submit.manual", "rule_list", "Always manual", ["tier_a", "fit_gte_85"]),
    ],
    schedule: [
      f("schedule.jobs.score", "schedule", "Score", { at: ["01:00"] }),
      f("schedule.quiet_hours", "time_range", "Quiet hours", { start: "09:00", end: "18:00" }, { nullable: true }),
    ],
  };
  const values: Record<string, unknown> = {};
  for (const list of Object.values(items)) for (const x of list) values[x.id] = x.default;
  return {
    section: {
      id: "runs",
      title: "Runs & schedule",
      help: "",
      files: ["pipeline"],
      groups: [
        { id: "budget", title: "Budget", help: "", items: items.budget },
        { id: "ranking", title: "Ranking", help: "", items: items.ranking },
        { id: "auto_submit", title: "Auto-submit", help: "", items: items.auto },
        { id: "schedule", title: "Schedule", help: "", items: items.schedule },
      ],
    },
    values,
    defaults: {},
    files: { pipeline: "config/pipeline.yaml" },
    version: "v1",
  };
}

export function safetyData(): SectionData {
  const levels = field({
    file: "targets",
    key: "safety.levels",
    control: "reason_levels",
    label: "Change a check's level",
    default: {},
    options: ["SCAM_PAYMENT_REQUEST", "GHOST_OLD_POST"],
  });
  const ats = field({
    file: "targets",
    key: "safety.auto_submit_ats",
    control: "tags",
    label: "Auto-submit on",
    default: ["greenhouse", "lever"],
    options: ["greenhouse", "lever", "ashby"],
  });
  return {
    section: {
      id: "safety",
      title: "Safety",
      help: "",
      files: ["targets"],
      groups: [
        { id: "ats", title: "Where auto-submit is allowed", help: "", items: [ats] },
        { id: "levels", title: "Check levels", help: "", items: [levels] },
      ],
    },
    values: { [ats.id]: ["greenhouse", "lever"], [levels.id]: { GHOST_OLD_POST: "info" } },
    defaults: {},
    files: { targets: "config/targets.yaml" },
    version: "v1",
  };
}

export interface Call {
  method: string;
  url: string;
  body: unknown;
  headers: Headers;
}

type Handler = (call: Call) => { status?: number; body: unknown } | undefined;

/** Stub fetch: each handler may answer a call; unanswered calls are 404. Returns the list of calls made. */
export function mockApi(...handlers: Handler[]): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const call: Call = {
        method: (init.method ?? "GET").toUpperCase(),
        url,
        body: init.body ? JSON.parse(String(init.body)) : undefined,
        headers: new Headers(init.headers),
      };
      calls.push(call);
      for (const h of handlers) {
        const r = h(call);
        if (r) {
          return new Response(JSON.stringify(r.body), {
            status: r.status ?? 200,
            headers: { "content-type": "application/json" },
          });
        }
      }
      return new Response(JSON.stringify({ detail: `no such endpoint: ${url}` }), { status: 404 });
    }),
  );
  return calls;
}

export const route =
  (method: string, url: string | RegExp, body: unknown | ((c: Call) => unknown), status = 200): Handler =>
  (c) => {
    const hit = c.method === method && (typeof url === "string" ? c.url === url : url.test(c.url));
    if (!hit) return undefined;
    return { status, body: typeof body === "function" ? (body as (c: Call) => unknown)(c) : body };
  };

export function sectionRoutes(...data: SectionData[]): Handler[] {
  return [
    route("GET", "/api/settings", { sections: SECTIONS }),
    ...data.map((d) => route("GET", `/api/settings/${d.section.id}`, d)),
  ];
}

export function renderSettings(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/settings/:section?", element: <SettingsPage /> },
      { path: "/runs", element: <p>Runs page</p> },
    ],
    { initialEntries: [path] },
  );
  const utils = render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...utils, router, qc };
}
