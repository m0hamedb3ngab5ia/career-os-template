import { Chip } from "../../kit/chips";
import { reasonText, reasonTone } from "./labels";
import styles from "./Runs.module.css";
import type { Reason } from "./types";

/** The ranking's "why" as chips: freshness blue, dream purple, deadline and retry orange, fit green. */
export function ReasonChips({ reasons }: { reasons: Reason[] }) {
  if (!reasons.length) return null;
  return (
    <span className={styles.chips}>
      {reasons.map((r) => (
        <Chip key={`${r.code}-${r.text}`} tone={reasonTone(r)}>
          {reasonText(r)}
        </Chip>
      ))}
    </span>
  );
}
