import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import { EmptyState } from "../../../kit/EmptyState";
import { useAdvice, useStorage } from "../api";
import { formatBytes, formatDuration, formatNumber, formatPercent } from "../format";
import type { Advice, StorageData } from "../types";
import { PruneNow } from "./PruneNow";
import { Recommendations } from "./Recommendations";
import { StorageChart, weeklySnapshots } from "./StorageChart";
import styles from "./storage.module.css";

const MB = 1024 * 1024;

function Tile({ label, value, sub, warn, small }: { label: string; value: ReactNode; sub?: ReactNode; warn?: boolean; small?: boolean }) {
  return (
    <section className={styles.tile} aria-label={label}>
      <div className={styles.tileLabel}>
        {warn ? (
          <span className={styles.warnIcon}>
            <AlertTriangle size={13} strokeWidth={1.8} aria-hidden="true" />
            <span className="sr-only">Warning:</span>
          </span>
        ) : null}
        {label}
      </div>
      <div className={styles.tileValue} data-size={small ? "small" : undefined}>
        {value}
      </div>
      {sub ? <div className={styles.tileSub}>{sub}</div> : null}
    </section>
  );
}

function StorageTiles({ st, advice }: { st: StorageData; advice: Advice | undefined }) {
  const budget = st.config.storage.budget_mb * MB;
  const share = budget ? st.total / budget : 0;
  const a = advice?.storage;
  const diskLow = st.disk.free_pct < st.config.storage.disk_free_warn_pct;
  const collecting = a && !a.ready ? `Collecting data: ${Math.floor(a.days)} of ${a.need_days} days` : "Loading…";
  return (
    <div className={styles.tiles}>
      <Tile
        label="career-os data"
        value={formatBytes(st.total)}
        sub={`of ${formatBytes(budget)} budget · ${formatPercent(share)}`}
        warn={share * 100 >= st.config.storage.warn_at_pct}
      />
      <Tile
        label="Growth"
        value={a?.ready && a.rate_per_day !== undefined ? `+${formatBytes(a.rate_per_day * 7)} per week` : "—"}
        sub={a?.ready ? `over ${formatNumber(Math.round(a.days))} days of snapshots` : collecting}
      />
      <Tile
        label="In 90 days"
        value={a?.ready && a.projection ? `≈ ${formatBytes(a.projection["90d"])}` : "—"}
        sub={
          a?.ready && a.projection
            ? a.projection["90d"] >= budget * (st.config.storage.warn_at_pct / 100)
              ? "reaches your warning level"
              : "stays under your warning level"
            : collecting
        }
      />
      <Tile
        label="Mac disk free"
        value={`${formatBytes(st.disk.free)} · ${formatPercent(st.disk.free_pct / 100)}`}
        sub={diskLow ? `below your ${st.config.storage.disk_free_warn_pct}% warning` : `warns under ${st.config.storage.disk_free_warn_pct}%`}
        warn={diskLow}
      />
    </div>
  );
}

function RunEfficiency({ advice }: { advice: Advice }) {
  const m = advice.runs.metrics;
  const score = m.score;
  const prepare = m.prepare;
  const kinds = [score, prepare].filter((x): x is NonNullable<typeof x> => Boolean(x));
  if (!kinds.length) {
    return (
      <section aria-labelledby="eff-title">
        <div className={styles.panelHead}>
          <h2 id="eff-title" className={styles.panelTitle}>
            Run efficiency
          </h2>
        </div>
        <EmptyState title="No score or prepare runs yet" headingLevel={3}>
          Numbers appear after the first runs finish.
        </EmptyState>
      </section>
    );
  }
  const attempts = kinds.reduce((a, k) => a + k.attempts, 0);
  const failed = kinds.reduce((a, k) => a + Math.round(k.failure_rate * k.attempts), 0);
  const runs = kinds.reduce((a, k) => a + k.runs, 0);
  const usage = kinds.reduce((a, k) => a + (k.stops.usage_limit ?? 0), 0);
  const budget = kinds.reduce((a, k) => a + k.budget_used * k.runs, 0) / Math.max(1, runs);
  const time = (k: typeof score) => (k && k.attempts ? formatDuration(k.avg_job_s) : "—");
  return (
    <section aria-labelledby="eff-title">
      <h2 id="eff-title" className={styles.effTitle}>
        Run efficiency · score and prepare runs
      </h2>
      <div className={styles.tiles} data-count="5">
        <Tile label="Time per job" value={`${time(score)} / ${time(prepare)}`} sub="score / prepare" small />
        <Tile label="Failure rate" value={formatPercent(attempts ? failed / attempts : 0)} sub={`${formatNumber(failed)} of ${formatNumber(attempts)} jobs`} />
        <Tile
          label="Scored → prepared"
          value={score?.prepare_share !== undefined && score.prepare_share !== null ? formatPercent(score.prepare_share) : "—"}
          sub="of jobs scored"
        />
        <Tile label="Budget used" value={formatPercent(budget)} sub="average per run" />
        <Tile label="Usage-limit stops" value={`${formatNumber(usage)} of ${formatNumber(runs)}`} sub="runs" warn={usage > 0} />
      </div>
    </section>
  );
}

/** Settings › Storage & efficiency, above the form: tiles, the weekly chart, recommendations, run efficiency and
 * Prune now. Reads `careeros storage --json` and `careeros advise --json` through the API. */
export function StorageOverview() {
  const storage = useStorage();
  const advice = useAdvice();
  const st = storage.data;
  const weeks = st ? weeklySnapshots(st.snapshots) : [];
  return (
    <>
      {storage.isError ? (
        <p role="alert" className={styles.panelSub}>
          Couldn't read storage. Check that careeros ui is running.
        </p>
      ) : st ? (
        <StorageTiles st={st} advice={advice.data} />
      ) : (
        <p className={styles.panelSub}>Measuring storage…</p>
      )}
      <section className={styles.panel} aria-labelledby="chart-title">
        <div className={styles.panelHead}>
          <h2 id="chart-title" className={styles.panelTitle}>
            Storage by category
          </h2>
          <span className={styles.panelSub}>Weekly snapshot after each prune · MB</span>
        </div>
        {weeks.length ? (
          <StorageChart weeks={weeks} />
        ) : (
          <EmptyState title="No storage snapshots yet" headingLevel={3}>
            One is recorded after each prune, or with careeros storage --snapshot.
          </EmptyState>
        )}
      </section>
      {advice.data ? <Recommendations advice={advice.data} /> : null}
      {advice.data ? <RunEfficiency advice={advice.data} /> : null}
      <PruneNow />
    </>
  );
}
