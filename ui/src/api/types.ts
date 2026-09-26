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
