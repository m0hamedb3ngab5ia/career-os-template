import { Link } from "react-router";
import { TierBadge } from "../../../kit/chips";
import { FieldRow } from "../FieldRow";
import { useSettingsForm } from "../form";
import { ResetButton } from "../GroupCard";
import styles from "../settings.module.css";
import type { FieldSchema, GroupSchema } from "../types";
import { isPolicy } from "../types";

const ORDER = ["auto_submit", "cover_letter", "outreach", "review_required", "description"];
const SHORT: Record<string, string> = { review_required: "You review", description: "Description" };

function TierCard({ group }: { group: GroupSchema }) {
  const form = useSettingsForm();
  const fields = group.items.filter((i): i is FieldSchema => !isPolicy(i));
  const byKey = (k: string) => fields.find((f) => f.key.endsWith(`.${k}`));
  const letter = group.title.replace(/^Tier\s+/, "");
  const desc = byKey("description");
  const headId = `tier-${letter.toLowerCase()}`;
  return (
    <section aria-labelledby={headId} className={styles.tierCard}>
      <div className={styles.tierHead}>
        <TierBadge tier={letter} />
        <h3 id={headId} className={styles.tierName}>
          {group.title}
        </h3>
        {desc ? <span className={styles.hint}>{String(form.value(desc.id) ?? "")}</span> : null}
      </div>
      {ORDER.map((k) => {
        const f = byKey(k);
        return f ? <FieldRow key={f.id} field={f} label={SHORT[k] ?? f.label} namePrefix={`${group.title}: `} compact /> : null;
      })}
      {fields
        .filter((f) => !ORDER.some((k) => f.key.endsWith(`.${k}`)))
        .map((f) => (
          <FieldRow key={f.id} field={f} namePrefix={`${group.title}: `} compact />
        ))}
      <div className={styles.tierFoot}>
        <ResetButton group={group} />
      </div>
    </section>
  );
}

/** Autonomy › Tiers: three cards side by side (A, B, C). Tier A's auto-submit is locked off by policy. */
export function TierCards({ groups }: { groups: GroupSchema[] }) {
  return (
    <section aria-labelledby="group-tiers">
      <div className={styles.groupHead}>
        <h2 id="group-tiers" className={styles.groupTitle}>
          Tiers
        </h2>
      </div>
      <div className={styles.tierGrid}>
        {groups.map((g) => (
          <TierCard key={g.id} group={g} />
        ))}
      </div>
      <p className={styles.groupNote}>
        These switches apply when you run Apply yourself. Scheduled runs have their own switch in{" "}
        <Link to="/settings/runs">Runs &amp; schedule</Link> (off).
      </p>
    </section>
  );
}
