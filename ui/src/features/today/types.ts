// Today screen types. API shapes are generated from the FastAPI OpenAPI schema (src/api/schema.gen.ts, see
// docs/UI.md "API types (generated)"): GET /api/status (services/status.py), /api/meta (services/meta.py) and
// /api/today (services/today.py). The run store's pause / catch-up files (open mappings in the schema) and the
// runs write replies stay hand-written here.
import type { components } from "../../api/schema.gen";
import type { Meta as ApiMeta, StatusSummary } from "../../api/types";

type Schemas = components["schemas"];

export type TileRow = Schemas["TileRow"];
/** One Action Item (services/actions.py ActionItem), the same shape /api/actions returns. */
export type ActionItem = Schemas["ActionItem"];
export type ResponseBreakdown = Schemas["ResponseBreakdown"];
export type Tiles = Schemas["Tiles"];
export type PipelineColumn = Schemas["PipelineColumnCount"];
export type RunRow = Schemas["RunRow"];
export type Meta = ApiMeta;
export type TodayData = Schemas["Today"];

/** runs/pause.json as the run store writes it. */
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

/** runs/catch_up.json as the run store writes it. */
export interface CatchUp {
  created_at?: string;
  updated_at?: string;
  kinds: Record<string, CatchUpKind>;
}

/** GET /api/status, with the pause / catch-up files described. */
export type TodayStatus = Omit<StatusSummary, "paused" | "catch_up"> & {
  paused: PauseState | null;
  catch_up: CatchUp | null;
};

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
