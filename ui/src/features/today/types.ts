// Hand-written types for the Today screen, matching the server's JSON:
// GET /api/status (src/careeros/ui/services/status.py), GET /api/meta (services/meta.py) and GET /api/today.
// Every field the server may leave out is optional here, so a partial or empty response still renders.
// TODO(OpenAPI): replace with generated types once the schema is exported.

export interface TileRow {
  job_id: string;
  company: string;
  role: string;
  /** A status code for applied / interviews / response-rate rows. */
  detail: string;
  when: string | null;
}

export interface ActionItem {
  id: string | number;
  job_id?: string | null;
  company: string;
  role?: string | null;
  what: string;
  type?: string | null;
  priority?: string | null;
  needs?: string | null;
  link?: string | null;
  created?: string | null;
  due?: string | null;
  due_reason?: string | null;
}

export interface ResponseBreakdown {
  /** interview | screening | offer | rejected | no_reply (applied in the window, no reply yet). */
  status: string;
  count: number;
  companies?: string[];
}

export interface Tiles {
  applied_week?: { value: number; since?: string | null; daily_cap?: number | null; rows?: TileRow[] };
  needs_you?: { value: number; high?: number; rows?: ActionItem[] };
  interviews?: { value: number; rows?: TileRow[] };
  response_rate?: {
    rate: number | null;
    responded: number;
    applied: number;
    days: number;
    definition?: string;
    ghost_days?: number;
    breakdown?: ResponseBreakdown[];
    rows?: TileRow[];
  };
}

export interface PipelineColumn {
  name: string;
  statuses: string[];
  count: number;
}

export interface RunRow {
  id: string;
  kind: string;
  trigger?: string | null;
  status?: string | null;
  stop_reason?: string | null;
  detail?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  duration_s?: number | null;
  attempted?: number | null;
  ok?: number | null;
  failed?: number | null;
  interrupted?: boolean;
}

export interface PauseState {
  until?: string | null;
  reason?: string | null;
  paused_at?: string | null;
}

export interface CatchUpKind {
  first_missed?: string | null;
  slots?: number;
  last_missed?: string | null;
}

export interface CatchUp {
  created_at?: string;
  updated_at?: string;
  kinds: Record<string, CatchUpKind>;
}

export interface TodayStatus {
  now?: string;
  tiles?: Tiles;
  pipeline?: { columns?: PipelineColumn[]; closed?: { count: number; by_status?: Record<string, number> } };
  counts?: { jobs?: number; action_items_open?: number; inbox?: number; contacts?: number };
  recent_runs?: RunRow[];
  paused?: PauseState | null;
  catch_up?: CatchUp | null;
  schedule?: { last_tick?: string | null; next?: Record<string, string | null>; error?: string | null };
  index?: { indexed_at?: string | null };
}

export interface Meta {
  statuses?: string[];
  presets?: { names?: string[]; recommended?: string; current?: string };
  pipeline?: { columns?: { name: string; statuses: string[] }[]; closed?: string[] };
  ui?: { theme?: string; undo_seconds?: number; page_size?: number };
}

export interface TodayData {
  actions?: ActionItem[];
  prepare_queue?: { total: number | null; error?: string | null };
}

export interface RunStarted {
  kind?: string;
  started?: boolean;
  pid?: number | null;
}

export interface CatchUpResult {
  status?: string;
  dismissed?: boolean;
  pending?: boolean;
  kinds?: string[];
  started?: boolean;
}
