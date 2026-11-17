import { Link } from "react-router";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { EmptyState } from "../../kit/EmptyState";
import { formatLongDate } from "../../lib/dates";
import { formatCount } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { errorText, useToday, useTodayStatus } from "./api";
import { buildSections, summary } from "./sections";
import { NeedsYou } from "./NeedsYou";
import { TopPicks } from "./TopPicks";
import { formatWhen } from "../../lib/dates";
import styles from "./Today.module.css";
import type { PipelineColumn, RunRow } from "./types";

/** Route `/` (docs/UI.md "Today"; mockup Main / TodayDark). */
export function TodayPage() {
  const now = useNow(60_000);
  const status = useTodayStatus();
  const today = useToday();
  const s = status.data;
  const picks = today.data?.top_picks ?? [];

  return (
    <Page title="Today" subtitle={formatLongDate(now)}>
      <div className={styles.stack}>
        {today.data ? <p className={styles.lead}>{summary(buildSections(today.data.actions ?? [], today.data.outreach ?? []))}</p> : null}
        {status.isError ? (
          <div className={styles.panel}>
            <EmptyState
              title="Couldn’t load automation status"
              action={
                <Button size="small" onClick={() => void status.refetch()}>
                  Retry
                </Button>
              }
            >
              {errorText(status.error)}
            </EmptyState>
          </div>
        ) : null}
        {picks.length ? <TopPicks picks={picks} /> : null}
        <NeedsYou />
        {s ? <Quiet runs={s.recent_runs ?? []} columns={s.pipeline?.columns ?? []} now={now} /> : null}
      </div>
    </Page>
  );
}

const plural = (n: number, word: string) => `${formatCount(n)} ${word}${n === 1 ? "" : "s"}`;

/** Outcome of a finished run in plain words; null = not worth showing (running, housekeeping). */
export function outcome(r: RunRow): string | null {
  if (r.status === "running" || !r.kind) return null;
  const n = r.ok ?? 0;
  const found = /(\d+) new/.exec(r.detail ?? "")?.[1];
  const text: Record<string, string> = {
    scout: found ? `Found ${plural(Number(found), "new matching job")}` : "Found new jobs",
    prepare: n ? `Prepared ${plural(n, "application")}` : "Prepared applications",
    apply: n ? `Filled ${plural(n, "application")}` : "Filled applications",
    score: n ? `Checked ${plural(n, "job")}` : "Checked new jobs",
  };
  const t = text[r.kind];
  if (!t) return null;
  return r.status === "failed" || r.status === "error" ? `${t}, stopped early` : t;
}

const sumOf = (cols: PipelineColumn[], statuses: string[]) =>
  cols.filter((c) => c.statuses.some((x) => statuses.includes(x))).reduce((t, c) => t + c.count, 0);

/** Footer: where the search stands and the last thing automation did. Quiet on purpose. */
function Quiet({ runs, columns, now }: { runs: RunRow[]; columns: PipelineColumn[]; now: Date }) {
  const last = runs.map((r) => ({ t: outcome(r), when: formatWhen(r.ended_at ?? r.started_at, now) })).find((r) => r.t);
  const active = sumOf(columns, ["applied", "screening", "interview"]);
  const fresh = sumOf(columns, ["found", "scored"]);
  const line = [`${plural(active, "application")} in progress`, `${formatCount(fresh)} new ${fresh === 1 ? "match" : "matches"}`].join(" · ");
  return (
    <footer className={styles.quiet}>
      <span>
        {line} · <Link to="/jobs">All jobs</Link>
      </span>
      {last?.t ? <span>Last run: {last.t.toLowerCase()}{last.when ? `, ${last.when}` : ""}</span> : null}
    </footer>
  );
}
