import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { Button } from "../../kit/Button";
import { errorText } from "../today/api";
import { type Change, changesKey, type Draft, revertChange, useChanges } from "./api";
import styles from "./Workspace.module.css";

/** A change's before/after: a text, or a node (bullet, entry) shown by its main text. */
const show = (v: unknown): string => {
  if (v == null) return "";
  if (typeof v !== "object") return String(v);
  const o = v as Record<string, unknown>;
  return String(o.text ?? o.company ?? o.name ?? o.school ?? o.title ?? o.id ?? "");
};
const VERB = { add: "added", edit: "edited", delete: "removed" } as const;

interface Props {
  rid: string;
  flush: () => Promise<boolean>;
  lock: (b: boolean) => void;
  onReverted: (d: Draft) => void;
  onClose: () => void;
}

/** History (DEC-015): the draft's change log, newest first. Revert appends an inverse change; refused (409) with both texts when the target moved on. */
export function History({ rid, flush, lock, onReverted, onClose }: Props) {
  const changes = useChanges(rid, true);
  const qc = useQueryClient();
  const revert = useMutation({
    mutationFn: async (c: Change) => {
      lock(true);  // an edit during the request would be overwritten by the reverted draft
      try {
        if (!(await flush())) throw new Error("Save your changes first (Retry save).");
        onReverted(await revertChange(rid, c.id));
      } finally { lock(false); }
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: changesKey(rid) }),
  });
  const list = (changes.data ?? []).slice().reverse();
  const done = new Set(list.map((c) => c.reverts).filter(Boolean));
  const err = revert.error;
  const conflict = err instanceof ApiError && err.status === 409
    ? (err.body as { detail?: { expected?: unknown; current?: unknown } }).detail : undefined;
  return (
    <aside className={styles.history} aria-label="History">
      <Button size="small" onClick={onClose}>← Back to suggestions</Button>
      {changes.isError ? <p role="alert" className={styles.alert}>Couldn’t load history: {errorText(changes.error)}</p> : null}
      {err ? (
        <p role="alert" className={styles.alert}>
          {conflict
            ? <>Can’t revert: this was changed afterwards. It was <q>{show(conflict.expected)}</q> and now reads <q>{show(conflict.current)}</q>. Edit it directly if you want the old text.</>
            : <>Couldn’t revert: {errorText(err)}</>}
        </p>
      ) : null}
      {changes.data && !list.length ? <p className={styles.muted}>No changes yet.</p> : null}
      <ul className={styles.changes}>
        {list.map((c) => (
          <li key={c.id} className={styles.change}>
            <p className={styles.muted}>{c.author === "ai" ? "Claude" : "You"} {c.reverts ? "reverted a change to" : VERB[c.op]} {c.target_id}{done.has(c.id) ? " · reverted" : ""}</p>
            <p><del>{show(c.before)}</del> <ins>{show(c.after)}</ins></p>
            <Button size="small" disabled={done.has(c.id) || revert.isPending} onClick={() => revert.mutate(c)}>Revert</Button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
