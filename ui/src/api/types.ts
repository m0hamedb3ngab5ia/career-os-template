// Hand-written minimal API types for the shell.
// TODO(slice 1 merge): replace with types generated from the FastAPI OpenAPI schema (openapi-typescript),
// committed and checked for drift in CI.

export interface StatusSummary {
  counts?: {
    jobs?: number;
    action_items_open?: number;
    inbox?: number;
  };
  index?: {
    /** ISO time of the last completed (re)index. */
    synced_at?: string | null;
  };
  tracker?: {
    /** ISO time the xlsx export was last written. */
    exported_at?: string | null;
  };
}
