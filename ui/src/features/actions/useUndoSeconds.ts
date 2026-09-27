import { useMeta } from "../../api/queries";

/** `pipeline.yaml: ui.undo_seconds` from /api/meta (the toast's own default until meta arrives). */
export function useUndoSeconds(): number | undefined {
  return useMeta().data?.ui.undo_seconds;
}
