import { TierBadge } from "../../kit/chips";
import { humanize } from "../../kit/labels";
import { formatCount } from "../../lib/format";
import { Card, Muted } from "./Card";
import { MatchesSection } from "./MatchesCard";
import styles from "./JobDetail.module.css";
import type { Score } from "./types";

/** Sub-score meters, one hue, the value printed beside each bar (only when score.json has a sub-score mapping). */
function SubScores({ scores }: { scores: Record<string, number> }) {
  const entries = Object.entries(scores).filter(([, v]) => typeof v === "number");
  if (entries.length === 0) return null;
  return (
    <ul className={styles.bars} aria-label="Sub-scores">
      {entries.map(([k, v]) => {
        const pct = Math.max(0, Math.min(100, v));
        return (
          <li key={k} className={styles.barRow}>
            <span className={styles.barLabel}>{humanize(k)}</span>
            <span className={styles.barTrack} aria-hidden="true">
              <span className={styles.barFill} style={{ width: `${pct}%` }} />
            </span>
            <span className={styles.barValue}>
              <span className="sr-only">: </span>
              {formatCount(v)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** Fit: the job score plus every résumé's match (was two cards; skills lived in both). */
export function ScoreCard({ jobId, score }: { jobId: string; score: Score | null }) {
  const matches = (
    <>
      <h3 className={styles.h3}>Résumé match</h3>
      <MatchesSection jobId={jobId} />
    </>
  );
  if (!score) {
    return (
      <Card title="Fit">
        <Muted>Not scored yet. Scoring runs after scout finds the job.</Muted>
        {matches}
      </Card>
    );
  }
  const fails = score.hard_filter_fails ?? [];
  const reasons = score.reasons ?? [];
  return (
    <Card
      title="Fit"
      aside={
        <span className={styles.bigNumber}>
          <span className="sr-only">Fit </span>
          {formatCount(score.fit)}
        </span>
      }
    >
      {score.sub_scores ? <SubScores scores={score.sub_scores} /> : null}
      <dl className={styles.facts}>
        <div>
          <dt>Tier</dt>
          <dd>
            <TierBadge tier={score.tier} />
          </dd>
        </div>
        {score.category ? (
          <div>
            <dt>Category</dt>
            <dd>{humanize(score.category)}</dd>
          </div>
        ) : null}
        <div>
          <dt>Hard filters</dt>
          <dd>{fails.length ? fails.join(", ") : "None failed"}</dd>
        </div>
      </dl>
      {reasons.length ? (
        <>
          <h3 className={styles.h3}>Why</h3>
          <ul className={styles.why} aria-label="Why this score">
            {reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </>
      ) : null}
      {matches}
    </Card>
  );
}
