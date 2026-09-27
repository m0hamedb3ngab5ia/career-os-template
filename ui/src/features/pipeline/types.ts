// GET /api/pipeline shapes, generated from the FastAPI OpenAPI schema (src/api/schema.gen.ts;
// services/pipeline.py). The URL filter state and the status write reply (job_actions.py) stay hand-written.
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

export type Hint = NonNullable<Schemas["Card"]["hint"]>;
export type Card = Schemas["Card"];
export type Column = Schemas["Column"];
export type Board = Schemas["Board"];

export interface Filters {
  tier: string;
  category: string;
  safety: string;
  location: string;
}

export interface StatusResult {
  job_id: string;
  status: string;
  previous: string | null;
}
