import { useState, type ReactNode } from "react";
import { ApiError } from "../../api/client";
import { useToast } from "../../kit/Toast";
import { useResetGroup } from "./api";
import { Button } from "../../kit/Button";
import { confirmFor, FieldRow, PolicyRow } from "./FieldRow";
import { useSettingsForm } from "./form";
import { equal } from "./format";
import styles from "./settings.module.css";
import type { GroupSchema, Values } from "./types";
import { isPolicy } from "./types";

/** True when "Reset to recommended" would change something in the group. */
export function useResettable(group: GroupSchema): boolean {
  const form = useSettingsForm();
  return group.items.some(
    (i) => !isPolicy(i) && !i.locked && !i.readonly && !i.personal && !equal(form.value(i.id), i.default),
  );
}

/** Reset keys that would turn on a switch that needs a confirm (auto-submit), with that confirm's wording. */
function riskyFlips(changes: Values, form: ReturnType<typeof useSettingsForm>) {
  return Object.keys(changes).flatMap((id) => {
    const f = form.field(id);
    const c = f ? confirmFor(f) : null;
    return c && changes[id] === true && form.value(id) !== true ? [{ id, ...c }] : [];
  });
}

export function ResetButton({ group, label = "Reset to recommended" }: { group: GroupSchema; label?: string }) {
  const form = useSettingsForm();
  const toast = useToast();
  const reset = useResetGroup(form.data.section.id);
  const can = useResettable(group);
  const [asking, setAsking] = useState<{ changes: Values; flips: { id: string; title: string; body: string }[] } | null>(
    null,
  );
  const qid = `reset-q-${group.id}`;
  return (
    <>
      <button
        type="button"
        className={styles.linkButton}
        disabled={!can || reset.isPending}
        aria-label={`${label}: ${group.title}`}
        onClick={() =>
          reset.mutate(group.id, {
            onSuccess: (r) => {
              const flips = riskyFlips(r.changes, form);
              if (flips.length) setAsking({ changes: r.changes, flips });
              else form.setMany(r.changes);
            },
            onError: (e) => toast.show({ message: e instanceof ApiError ? e.message : "Couldn't reset. Try again." }),
          })
        }
      >
        {reset.isPending ? "Resetting…" : label}
      </button>
      {asking ? (
        <div
          className={`${styles.confirmTurnOn} ${styles.resetConfirm}`}
          role="alertdialog"
          aria-labelledby={qid}
          onKeyDown={(e) => e.key === "Escape" && setAsking(null)}
        >
          <div id={qid} className={styles.confirmTitle}>
            {asking.flips.map((f) => f.title).join(" ")}
          </div>
          <div>{asking.flips.map((f) => f.body).join(" ")}</div>
          <div className={styles.confirmActions}>
            <Button
              size="small"
              autoFocus
              onClick={() => {
                const skip = new Set(asking.flips.map((f) => f.id));
                const rest = Object.fromEntries(Object.entries(asking.changes).filter(([k]) => !skip.has(k)));
                if (Object.keys(rest).length) form.setMany(rest);
                setAsking(null);
              }}
            >
              Cancel
            </Button>
            <Button
              size="small"
              variant="primary"
              onClick={() => {
                form.setMany(asking.changes);
                setAsking(null);
              }}
            >
              Turn on
            </Button>
          </div>
        </div>
      ) : null}
    </>
  );
}

interface GroupCardProps {
  group: GroupSchema;
  /** Replace the default rows (custom renderers). */
  children?: ReactNode;
  /** A note under the card; defaults to the group's help text. */
  note?: ReactNode;
  titleId?: string;
}

/** One card of a Settings page: a small heading with "Reset to recommended", then grouped rows. */
export function GroupCard({ group, children, note, titleId }: GroupCardProps) {
  const id = titleId ?? `group-${group.id}`;
  const shown = note ?? (group.help || null);
  return (
    <section aria-labelledby={id}>
      <div className={styles.groupHead}>
        <h2 id={id} className={styles.groupTitle}>
          {group.title}
        </h2>
        <ResetButton group={group} />
      </div>
      <div className={styles.card}>
        {children ??
          group.items.map((item, i) =>
            isPolicy(item) ? <PolicyRow key={`p${i}`} item={item} /> : <FieldRow key={item.id} field={item} />,
          )}
      </div>
      {shown ? <p className={styles.groupNote}>{shown}</p> : null}
    </section>
  );
}
