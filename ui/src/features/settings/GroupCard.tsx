import type { ReactNode } from "react";
import { ApiError } from "../../api/client";
import { useToast } from "../../kit/Toast";
import { useResetGroup } from "./api";
import { FieldRow, PolicyRow } from "./FieldRow";
import { useSettingsForm } from "./form";
import { equal } from "./format";
import styles from "./settings.module.css";
import type { GroupSchema } from "./types";
import { isPolicy } from "./types";

/** True when "Reset to recommended" would change something in the group. */
export function useResettable(group: GroupSchema): boolean {
  const form = useSettingsForm();
  return group.items.some(
    (i) => !isPolicy(i) && !i.locked && !i.readonly && !i.personal && !equal(form.value(i.id), i.default),
  );
}

export function ResetButton({ group, label = "Reset to recommended" }: { group: GroupSchema; label?: string }) {
  const form = useSettingsForm();
  const toast = useToast();
  const reset = useResetGroup(form.data.section.id);
  const can = useResettable(group);
  return (
    <button
      type="button"
      className={styles.linkButton}
      disabled={!can || reset.isPending}
      aria-label={`${label}: ${group.title}`}
      onClick={() =>
        reset.mutate(group.id, {
          onSuccess: (r) => form.setMany(r.changes),
          onError: (e) => toast.show({ message: e instanceof ApiError ? e.message : "Couldn't reset. Try again." }),
        })
      }
    >
      {reset.isPending ? "Resetting…" : label}
    </button>
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
