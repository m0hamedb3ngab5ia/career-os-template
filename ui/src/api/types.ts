// API types for the shell, generated from the FastAPI OpenAPI schema (ui/openapi.json → src/api/schema.gen.ts).
// Regenerate after a backend change: `python -m careeros.ui.openapi > ui/openapi.json && npm run gen:api`
// (docs/UI.md). Endpoints still returning an untyped dict keep hand-written types in src/features/*/types.ts.
import type { components } from "./schema.gen";

type Schemas = components["schemas"];

/** GET /api/status (src/careeros/ui/services/status.py: Status). */
export type StatusSummary = Schemas["Status"];

/** GET /api/meta (src/careeros/ui/services/meta.py: Meta): every code the UI renders, plus the ui settings. */
export type Meta = Schemas["Meta"];

/** GET /api/catalogue (src/careeros/ui/services/catalogue.py: Catalogue): docs/CATALOGUE.md as sections and rows (REQ-165). */
export type Catalogue = Schemas["Catalogue"];
export type CatalogueSection = Schemas["CatalogueSection"];
export type CatalogueRow = Schemas["CatalogueRow"];
