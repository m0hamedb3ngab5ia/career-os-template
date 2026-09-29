import { Filter } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ApiError } from "../../api/client";
import { useMeta } from "../../api/queries";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { EmptyState } from "../../kit/EmptyState";
import { HUMAN, SAFETY, STATUSES, describeCode, humanize } from "../../kit/labels";
import { Listbox } from "../../kit/Listbox";
import { Sheet } from "../../kit/Sheet";
import type { MenuItem } from "../../kit/Menu";
import { useToast } from "../../kit/Toast";
import { formatCount } from "../../lib/format";
import { useBoard, useSetStatus } from "./api";
import { JobCard } from "./JobCard";
import styles from "./Pipeline.module.css";
import { StatusChooser } from "./StatusChooser";
import type { Card, Filters } from "./types";

const CLOSED = "Closed";
const APPLICATIONS = ["applied", "screening", "interview", "offer"];
// Applied records the date applied and counts toward the daily cap, so it is confirmed first and has no Undo.
const APPLIED = "applied";
const FILTER_KEYS = ["tier", "category", "safety", "location"] as const;

function statusLabel(s: string): string {
  return describeCode(STATUSES, s).label;
}

function humanStatus(s: string): string {
  return (HUMAN.status as Record<string, string>)[s] ?? statusLabel(s);
}

/** Jobs (every tab) filtered to one column value or date range: the funnel's "open the list" link. */
function jobsHref(field: string, value: string): string {
  return `/jobs?${new URLSearchParams({ tab: "all", [`f.${field}`]: value })}`;
}

function problem(e: unknown): string {
  return e instanceof ApiError ? e.message : "Couldn't reach careeros ui. Is it still running?";
}

interface Target {
  name: string;
  statuses: string[];
}

export function PipelinePage() {
  const [params, setParams] = useSearchParams();
  const filters: Filters = { tier: "", category: "", safety: "", location: "" };
  for (const k of FILTER_KEYS) filters[k] = params.get(k) ?? "";
  const { data: board, isPending, error } = useBoard(filters);
  const meta = useMeta().data;
  const setStatus = useSetStatus();
  const toast = useToast();
  const [choosing, setChoosing] = useState<{ card: Card; target: Target } | null>(null);
  const [confirmApplied, setConfirmApplied] = useState<Card | null>(null);
  const titleId = useId();
  // A moved card remounts in its new group: once the board shows it there, focus its Move to… again.
  const [refocus, setRefocus] = useState<{ jobId: string; status: string } | null>(null);
  useEffect(() => {
    if (!refocus || !board) return;
    const moved = board.applications.find((c) => c.job_id === refocus.jobId);
    if (moved && moved.status !== refocus.status) return; // not refetched yet
    const el = [...document.querySelectorAll<HTMLElement>("[data-job-id]")].find((n) => n.dataset.jobId === refocus.jobId);
    el?.querySelector<HTMLElement>("[data-move] button")?.focus();
    setRefocus(null);
  }, [board, refocus]);

  function setParam(k: string, v: string) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (v) next.set(k, v);
        else next.delete(k);
        return next;
      },
      { replace: true },
    );
  }

  const closedStatuses = meta?.pipeline.closed ?? Object.keys(board?.closed.by_status ?? {});

  function move(card: Card, status: string) {
    const company = card.company || card.job_id;
    setStatus.mutate(
      { jobId: card.job_id, status, note: `moved on the pipeline to ${statusLabel(status)}` },
      {
        onSuccess: (r) => {
          setRefocus({ jobId: card.job_id, status });
          toast.show({
            message: `Moved ${company} to ${statusLabel(status)}`,
            seconds: meta?.ui.undo_seconds,
            onUndo:
              r.previous && status !== APPLIED
                ? () =>
                    setStatus.mutate(
                      { jobId: card.job_id, status: r.previous!, note: "undo: pipeline move" },
                      {
                        onSuccess: () => setRefocus({ jobId: card.job_id, status: r.previous! }),
                        onError: (e) => toast.show({ message: `Undo failed: ${problem(e)}` }),
                      },
                    )
                : undefined,
          });
        },
        onError: (e) => toast.show({ message: `Couldn't move ${company}: ${problem(e)}` }),
      },
    );
  }

  function go(card: Card, status: string) {
    if (status === APPLIED) setConfirmApplied(card);
    else move(card, status);
  }

  function requestMove(card: Card, target: Target) {
    const options = target.statuses.filter((s) => s !== card.status);
    if (options.length === 0) return;
    if (options.length === 1) go(card, options[0]!);
    else setChoosing({ card, target: { ...target, statuses: options } });
  }

  const targets: Target[] = [
    ...APPLICATIONS.map((st) => ({ name: statusLabel(st), statuses: [st] })),
    ...(closedStatuses.length ? [{ name: CLOSED, statuses: closedStatuses }] : []),
  ];

  function moveItems(card: Card): MenuItem[] {
    return targets.map((t) => ({
      key: t.name,
      label: t.name === CLOSED ? "Closed…" : t.name,
      disabled: t.statuses.every((s) => s === card.status),
      onSelect: () => requestMove(card, t),
    }));
  }

  const closedParts = Object.entries(board?.closed.by_status ?? {}).map(
    ([s, n]) => `${statusLabel(s).toLowerCase()} ${formatCount(n)}`,
  );

  const opt = (values: { value: string; label: string }[]) => [{ value: "", label: "All" }, ...values];
  const filterOptions = {
    tier: opt((meta?.tiers ?? ["A", "B", "C"]).map((t) => ({ value: t, label: t }))),
    category: opt((board?.options.categories ?? []).map((c) => ({ value: c, label: humanize(c) }))),
    safety: opt((meta?.safety_verdicts ?? Object.keys(SAFETY)).map((s) => ({ value: s, label: describeCode(SAFETY, s).label }))),
    location: opt((board?.options.locations ?? []).map((l) => ({ value: l.value, label: l.value }))),
  };
  // keep a filter that is in the URL selectable even when no job has that value any more
  for (const k of FILTER_KEYS) {
    if (filters[k] && !filterOptions[k].some((o) => o.value === filters[k])) filterOptions[k].push({ value: filters[k], label: filters[k] });
  }

  return (
    <Page title="Pipeline" subtitle="How jobs move from discovery to an offer">
      {error ? (
        <EmptyState title="Couldn't load the pipeline">{problem(error)}</EmptyState>
      ) : isPending || !board ? null : (
        <>
          <h2 className={styles.sectionTitle} id={`${titleId}-funnel`}>
            Automation funnel
          </h2>
          <nav aria-labelledby={`${titleId}-funnel`}>
            <ul className={styles.funnel}>
              {board.funnel.map((f) => (
                <li key={f.status}>
                  <Link to={jobsHref("status", f.status)} className={styles.stage}>
                    <span className={styles.stageCount}>{formatCount(f.count)}</span> <span>{humanStatus(f.status)}</span>
                  </Link>
                </li>
              ))}
              <li>
                <Link to={jobsHref("applied_at", `${board.submitted.since}..`)} className={styles.stage}>
                  <span className={styles.stageCount}>{formatCount(board.submitted.count)}</span>{" "}
                  <span>Submitted this week</span>
                </Link>
              </li>
            </ul>
          </nav>

          <h2 className={styles.sectionTitle}>Applications</h2>
          <div className={styles.toolbar}>
            <span className={styles.filterIcon}>
              <Filter size={14} strokeWidth={1.7} aria-hidden="true" />
            </span>
            {FILTER_KEYS.map((k) => (
              <Listbox
                key={k}
                label={k[0]!.toUpperCase() + k.slice(1)}
                labelPlacement="inline"
                value={filters[k]}
                options={filterOptions[k]}
                onValueChange={(v) => setParam(k, v)}
              />
            ))}
            <Link to={jobsHref("status", closedStatuses.join(","))} className={styles.closed}>
              Closed: {formatCount(board.closed.count)}
              {closedParts.length ? ` (${closedParts.join(" · ")})` : ""}
            </Link>
          </div>
          <div className={styles.board}>
            {APPLICATIONS.map((st) => {
              const cards = board.applications.filter((c) => c.status === st);
              const id = `${titleId}-${st}`;
              return (
                <section key={st} className={styles.column} aria-labelledby={id}>
                  <h3 className={styles.columnTitle} id={id}>
                    {statusLabel(st)} <span className={styles.count}>{formatCount(cards.length)}</span>
                  </h3>
                  {cards.length ? (
                    <ul className={styles.cards}>
                      {cards.map((card) => (
                        <li key={card.job_id}>
                          <JobCard
                            card={card}
                            moveItems={moveItems(card)}
                            pending={setStatus.isPending && setStatus.variables?.jobId === card.job_id}
                          />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className={styles.emptyColumn}>None yet</p>
                  )}
                </section>
              );
            })}
          </div>
        </>
      )}
      {choosing ? (
        <StatusChooser
          company={choosing.card.company || choosing.card.job_id}
          target={choosing.target.name}
          statuses={choosing.target.statuses}
          onClose={() => setChoosing(null)}
          onChoose={(s) => {
            const c = choosing.card;
            setChoosing(null);
            go(c, s);
          }}
        />
      ) : null}
      {confirmApplied ? (
        <Sheet
          open
          title={`Mark ${confirmApplied.company || confirmApplied.job_id} applied?`}
          closeLabel="Cancel"
          onClose={() => setConfirmApplied(null)}
          footer={
            <Button
              variant="primary"
              onClick={() => {
                const c = confirmApplied;
                setConfirmApplied(null);
                move(c, APPLIED);
              }}
            >
              Mark applied
            </Button>
          }
        >
          <p>
            This records today as the date applied and counts toward the daily application cap. There is no Undo; to
            change it later, set the status again from the job.
          </p>
        </Sheet>
      ) : null}
    </Page>
  );
}
