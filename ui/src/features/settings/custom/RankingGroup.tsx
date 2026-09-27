import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../../api/client";
import { SegmentedControl } from "../../../kit/SegmentedControl";
import { useRankingPreview } from "../api";
import { FieldRow } from "../FieldRow";
import { useSettingsForm } from "../form";
import { formatNumber } from "../format";
import { GroupCard } from "../GroupCard";
import styles from "../settings.module.css";
import type { FieldSchema, GroupSchema } from "../types";
import { isPolicy } from "../types";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function Preview({ weights, dirty }: { weights: Record<string, number>; dirty: boolean }) {
  const [kind, setKind] = useState<"score" | "prepare">("score");
  const debounced = useDebounced(weights, 250);
  const q = useRankingPreview(kind, debounced, true);
  let body;
  if (q.isError) {
    const why = q.error instanceof ApiError ? q.error.message : "the server didn't answer";
    body = <p className={styles.hint}>The preview isn't available right now: {why}.</p>;
  } else if (!q.data) {
    body = <p className={styles.hint}>Ranking…</p>;
  } else if (!q.data.items.length) {
    body = <p className={styles.hint}>No jobs are waiting to be {kind === "score" ? "scored" : "prepared"}.</p>;
  } else {
    body = (
      <ol className={styles.previewList} aria-busy={q.isFetching || undefined}>
        {q.data.items.map((r) => (
          <li key={r.job_id} className={styles.previewItem}>
            <span>
              <span className={styles.hint}>{r.rank}.</span> {r.company}
              <span className={styles.previewWhy}>{r.why}</span>
            </span>
            <span className={styles.num}>{formatNumber(r.score, { maximumFractionDigits: 1 })}</span>
          </li>
        ))}
      </ol>
    );
  }
  return (
    <aside className={styles.preview} aria-labelledby="ranking-preview-title">
      <h3 id="ranking-preview-title" className={styles.previewTitle}>
        Preview {dirty ? "with these weights" : "of the next run"}
      </h3>
      <SegmentedControl label="Run kind" value={kind} onValueChange={(v) => setKind(v as "score" | "prepare")}>
        <SegmentedControl.Option value="score">Score</SegmentedControl.Option>
        <SegmentedControl.Option value="prepare">Prepare</SegmentedControl.Option>
      </SegmentedControl>
      <div aria-live="polite">{body}</div>
      {q.data && q.data.total > q.data.items.length ? (
        <p className={styles.hint}>
          Top {q.data.items.length} of {formatNumber(q.data.total)} waiting. Within one company, the best fit still wins
          the company slot.
        </p>
      ) : null}
    </aside>
  );
}

/** Runs › Ranking: the weights (sliders and numbers) beside a live preview of the next jobs with the draft
 * weights. Nothing is saved until Save. */
export function RankingGroup({ group }: { group: GroupSchema }) {
  const form = useSettingsForm();
  const fields = group.items.filter((i): i is FieldSchema => !isPolicy(i));
  const values = fields.map((f) => form.value(f.id));
  const weights = useMemo(() => {
    const out: Record<string, number> = {};
    fields.forEach((f, i) => {
      const v = values[i];
      if (typeof v === "number" && Number.isFinite(v) && v >= 0) out[f.key.split(".").at(-1)!] = v;
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(values)]);
  const dirty = fields.some((f) => f.id in form.changes);
  return (
    <GroupCard group={{ ...group, title: "Ranking · what gets scored first" }}>
      <div className={styles.ranking}>
        <div className={styles.weights}>
          {fields.map((f) => (
            <FieldRow key={f.id} field={f} />
          ))}
        </div>
        <Preview weights={weights} dirty={dirty} />
      </div>
    </GroupCard>
  );
}
