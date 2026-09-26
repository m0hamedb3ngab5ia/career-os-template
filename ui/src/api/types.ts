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

/** GET /api/meta (src/careeros/ui/services/meta.py); only the fields the screens read so far. */
export interface Meta {
  statuses?: string[];
  ui?: { theme?: string; undo_seconds?: number; page_size?: number };
}
