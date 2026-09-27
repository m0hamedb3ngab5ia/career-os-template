// Hand-written minimal API types for the shell, matching src/careeros/ui/services/status.py on feat/ui-server.
// TODO(slice 1 merge): replace with types generated from the FastAPI OpenAPI schema (openapi-typescript),
// committed and checked for drift in CI.

export interface StatusSummary {
  now?: string;
  counts?: {
    jobs?: number;
    action_items_open?: number;
    inbox?: number;
    contacts?: number;
  };
  index?: {
    /** ISO time of the last completed (re)index. */
    indexed_at?: string | null;
  };
}

/** GET /api/meta (src/careeros/ui/services/meta.py): every code the UI renders, plus the ui settings. */
export interface Meta {
  statuses: string[];
  tiers: string[];
  priorities: string[];
  action_types: string[];
  action_needs: string[];
  safety_verdicts: string[];
  pipeline: { columns: { name: string; statuses: string[] }[]; closed: string[]; card_limit: number };
  ui: { theme: string; undo_seconds: number; page_size: number; due_soon_hours: number };
}
