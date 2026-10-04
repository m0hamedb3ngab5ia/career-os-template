import { useId, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Page } from "../../../app/PageHeader";
import { Button } from "../../../kit/Button";
import { SelectField, TextField } from "../../../kit/FormField";
import { NumberInput } from "../../../kit/inputs";
import { SegmentedControl } from "../../../kit/SegmentedControl";
import { useJobsList } from "../../jobs/api";
import { sortCaption, useJobsView, type Filters } from "../../jobs/urlState";
import { useSection } from "../../settings/api";
import { MAX_JOBS, useBatchPreview, useStartBatch, type StopAt } from "./api";
import styles from "./batch.module.css";
import { HARD_RULES, STOP_POINTS, confirmSentence, filterSummary } from "./copy";

const RANKINGS = [
  { value: "-fit", label: "Highest match" },
  { value: "-found_at", label: "Most recent" },
  { value: "found_at", label: "Oldest first" },
];
const QUANTITIES = ["10", "25", "50", "custom"];

function message(e: unknown) {
  return e instanceof Error ? e.message : "Something went wrong.";
}

/** Pipeline › New batch (docs/design/ui-redesign.md §4): pick jobs by the Jobs filters (or `?ids=` handed over
 *  from Jobs), choose where to stop, check the exact list, then confirm. Nothing runs before "Start batch". */
export function BatchBuilderPage() {
  const [view, update] = useJobsView();
  const [params] = useSearchParams();
  const ids = [...new Set((params.get("ids") ?? "").split(",").map((s) => s.trim()).filter(Boolean))];
  const fromFilters = ids.length === 0;
  const [defaultName] = useState(() => `Batch — ${new Date().toLocaleDateString("en-US", { month: "short", day: "numeric" })}`);
  const [name, setName] = useState(defaultName);
  const [qty, setQty] = useState("25");
  const [custom, setCustom] = useState<number | null>(100);
  const [stop, setStop] = useState<StopAt>("prepare");
  const [off, setOff] = useState<ReadonlySet<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const reasonId = useId();

  const runs = useSection("runs");
  const autoSubmit = runs.data?.values["runs.auto_submit.enabled"] === true;
  const autoOff = runs.data !== undefined && !autoSubmit; // only say "off" once settings have loaded
  const limit = qty === "custom" ? Math.min(Math.max(Math.round(custom ?? 1), 1), MAX_JOBS) : Number(qty);
  const jobs = useJobsList({ tab: view.tab, q: view.q, location: view.location, filters: view.filters, sort: view.sort, limit }, fromFilters);
  const first = jobs.data?.pages[0];
  const candidates = fromFilters ? (first?.items.map((j) => j.job_id) ?? []) : ids.slice(0, MAX_JOBS);
  const preview = useBatchPreview(candidates, stop);
  const selected = preview.data?.selected ?? [];
  const chosen = selected.filter((j) => !off.has(j.job_id)).map((j) => j.job_id);
  const start = useStartBatch();
  // keepPreviousData: while refetching, the list and count are from the old stop/filters, so starting waits.
  const stale = preview.isPlaceholderData || preview.isFetching || jobs.isFetching;

  const summary = filterSummary(view);
  const source = fromFilters ? (summary ? `filters: ${summary}` : "") : "from your Jobs selection";
  const rankings = RANKINGS.some((r) => r.value === view.sort) ? RANKINGS : [...RANKINGS, { value: view.sort, label: `As in Jobs (${sortCaption(view.sort)})` }];
  const setFilter = (field: "fit" | "found_at", min: string) => {
    const filters: Filters = { ...view.filters };
    const cur = filters[field];
    const max = cur?.kind === "range" ? cur.max : "";
    if (min || max) filters[field] = { kind: "range", min, max };
    else delete filters[field];
    update({ filters }, true);
  };
  const toggle = (id: string) =>
    setOff((s) => {
      const next = new Set(s);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  const pickStop = (v: string) => {
    setStop(v as StopAt);
    setConfirming(false);
  };

  if (start.data?.id) {
    return (
      <Page title="New batch" subtitle="The batch is running · follow its progress">
        <p role="status">
          {start.data.name ?? "Batch"} started.{" "}
          <Link to={`/pipeline/batch/${encodeURIComponent(start.data.id)}`}>Follow batch progress</Link>
        </p>
      </Page>
    );
  }

  return (
    <Page title="New batch" subtitle="Pick jobs, choose where the batch stops, check the list, then start it">
      <div className={styles.builder}>
        <section aria-labelledby={`${reasonId}-stop`} className={styles.section}>
          <h2 id={`${reasonId}-stop`}>Stop after</h2>
          <SegmentedControl label="Stop after" value={stop} onValueChange={pickStop}>
            {STOP_POINTS.map((s) => (
              <SegmentedControl.Option key={s.value} value={s.value} disabled={s.value === "submit" && !autoSubmit}
                describedBy={s.value === "submit" && autoOff ? reasonId : undefined}>
                {s.label}
              </SegmentedControl.Option>
            ))}
          </SegmentedControl>
          {autoOff ? (
            <p id={reasonId} className={styles.note}>
              Auto-submit is off in Settings, so a batch can fill applications but not submit them.{" "}
              <Link to="/settings/runs">Change in Settings</Link>
            </p>
          ) : null}
          <ul className={styles.rules}>
            {HARD_RULES.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </section>

        <section aria-labelledby={`${reasonId}-jobs`} className={styles.section}>
          <h2 id={`${reasonId}-jobs`}>Jobs</h2>
          {fromFilters ? (
            <>
              <div className={styles.fields}>
                <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
                <TextField label="Search" value={view.q} onChange={(e) => update({ q: e.target.value }, true)} />
                <TextField label="Match at least" type="number" min={0} max={100} value={view.filters.fit?.kind === "range" ? view.filters.fit.min : ""}
                  onChange={(e) => setFilter("fit", e.target.value)} />
                <TextField label="Found since" type="date" value={view.filters.found_at?.kind === "range" ? view.filters.found_at.min : ""}
                  onChange={(e) => setFilter("found_at", e.target.value)} />
                <SelectField label="Rank by" options={rankings} value={view.sort} onChange={(e) => update({ sort: e.target.value }, true)} />
              </div>
              <div className={styles.row}>
                <SegmentedControl label="How many" value={qty} onValueChange={setQty}>
                  {QUANTITIES.map((q) => <SegmentedControl.Option key={q} value={q}>{q === "custom" ? "Custom" : q}</SegmentedControl.Option>)}
                </SegmentedControl>
                {qty === "custom" ? (
                  <NumberInput aria-label="Number of jobs" integer min={1} max={MAX_JOBS} value={custom} onValueChange={setCustom} />
                ) : null}
              </div>
              <p role="status" className={styles.note}>
                {first ? `${first.total} jobs match · taking the top ${Math.min(limit, first.total)}` : "Counting jobs…"}
                {summary ? ` · ${summary}` : ""} · <Link to={`/jobs?${params}`}>More filters in Jobs</Link>
              </p>
            </>
          ) : (
            <div className={styles.fields}>
              <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
              <p className={styles.note}>{ids.length} jobs from your Jobs selection</p>
            </div>
          )}
          {jobs.error || preview.error ? <p role="alert">{message(jobs.error ?? preview.error)}</p> : null}

          <fieldset className={styles.list} aria-label="Jobs in this batch">
            <p>{`${chosen.length} of ${selected.length} selected`}</p>
            {selected.map((j) => (
              <label key={j.job_id} className={styles.job}>
                <input type="checkbox" checked={!off.has(j.job_id)} onChange={() => toggle(j.job_id)} />
                <span>
                  {j.company} · {j.title}
                  {j.fit === null || j.fit === undefined ? "" : ` · ${j.fit}% match`}
                </span>
                <span className={styles.why}>{j.why}</span>
              </label>
            ))}
          </fieldset>
          {preview.data?.excluded.length ? (
            <details className={styles.excluded}>
              <summary>Not included ({preview.data.excluded.length})</summary>
              <ul>
                {preview.data.excluded.map((x) => <li key={x.job_id}>{x.job_id}: {x.reason}</li>)}
              </ul>
            </details>
          ) : null}
        </section>

        {confirming ? (
          <section aria-label="Confirm batch" className={styles.confirm}>
            <p>{confirmSentence(chosen.length, stop, source)}</p>
            {start.error ? (
              <p role="alert">
                {start.savedId ? (
                  <>
                    Batch saved but not started: {message(start.error)}{" "}
                    <Link to={`/pipeline/batch/${encodeURIComponent(start.savedId)}`}>Open saved batch</Link>
                  </>
                ) : message(start.error)}
              </p>
            ) : null}
            <div className={styles.row}>
              <Button variant="primary" pending={start.isPending} pendingLabel="Starting…" disabled={stale && !start.savedId}
                onClick={() => start.mutate({ jobIds: chosen, stopAt: stop, name: name.trim() || defaultName })}>
                Start batch
              </Button>
              <Button onClick={() => setConfirming(false)}>Back</Button>
            </div>
          </section>
        ) : (
          <div className={styles.row}>
            <Button variant="primary" disabled={chosen.length === 0 || stale} onClick={() => setConfirming(true)}>
              Review and start
            </Button>
          </div>
        )}
      </div>
    </Page>
  );
}
