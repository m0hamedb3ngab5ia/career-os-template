import { AlertTriangle, Lightbulb } from "lucide-react";
import { useState } from "react";
import { ApiError } from "../../../api/client";
import { Button } from "../../../kit/Button";
import { useToast } from "../../../kit/Toast";
import { useApplyAdvice } from "../api";
import type { Advice, Recommendation } from "../types";
import styles from "./storage.module.css";

// Dismissed recommendations are a per-browser convenience: kept in localStorage, never on the server. Storage can
// be missing or throw (private windows, blocked site data); the list still works, it just forgets on reload.
const KEY = "careeros.settings.dismissed-advice";

export function loadDismissed(): string[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    const v: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function saveDismissed(ids: string[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(ids));
  } catch {
    // storage unavailable: dismissal lasts until reload
  }
}

function showValue(v: unknown): string {
  return v === null || v === undefined ? "off" : String(v);
}

export function changeText(r: Recommendation): string | null {
  return r.change ? `${r.change.path}: ${showValue(r.change.from)} → ${showValue(r.change.to)}` : null;
}

export function Recommendations({ advice }: { advice: Advice }) {
  const toast = useToast();
  const apply = useApplyAdvice();
  const [dismissed, setDismissed] = useState<string[]>(loadDismissed);
  const [lastDismissed, setLastDismissed] = useState<Recommendation | null>(null);
  const recs = advice.recommendations.filter((r) => !dismissed.includes(r.id));
  const st = advice.storage;

  function dismiss(r: Recommendation) {
    const next = [...dismissed, r.id];
    setDismissed(next);
    saveDismissed(next);
    setLastDismissed(r);
  }

  function undo() {
    if (!lastDismissed) return;
    const next = dismissed.filter((d) => d !== lastDismissed.id);
    setDismissed(next);
    saveDismissed(next);
    setLastDismissed(null);
  }

  return (
    <section className={styles.panel} aria-labelledby="recs-title">
      <div className={styles.panelHead}>
        <h2 id="recs-title" className={styles.panelTitle}>
          Recommendations
        </h2>
        <span className={styles.panelSub}>
          {st.ready
            ? "Apply writes the change to pipeline.yaml (comments kept); nothing changes without the click"
            : `Collecting data: ${Math.floor(st.days)} of ${st.need_days} days of storage snapshots`}
        </span>
      </div>
      {lastDismissed ? (
        <div role="status" className={styles.undoLine}>
          <span>Dismissed: {lastDismissed.title}</span>
          <Button size="small" onClick={undo}>
            Undo
          </Button>
        </div>
      ) : null}
      {recs.length === 0 ? (
        <p className={styles.quiet}>
          {advice.recommendations.length
            ? "All caught up. You dismissed the rest."
            : "All caught up. Settings look right for how you use career-os."}
        </p>
      ) : (
        <ul className={styles.recs}>
          {recs.map((r) => {
            const change = changeText(r);
            const Icon = r.severity === "warn" ? AlertTriangle : Lightbulb;
            const applying = apply.isPending && apply.variables === r.id;
            return (
              <li key={r.id} className={styles.rec}>
                <span className={styles.recIcon} data-severity={r.severity}>
                  <Icon size={14} strokeWidth={1.8} aria-hidden="true" />
                  <span className="sr-only">{r.severity === "warn" ? "Warning" : "Tip"}</span>
                </span>
                <div className={styles.recBody}>
                  <div className={styles.recTitle}>{r.title}</div>
                  <div className={styles.recWhy}>{r.why}</div>
                  {change ? (
                    <code className={styles.change} translate="no">
                      {change}
                    </code>
                  ) : null}
                </div>
                <div className={styles.recActions}>
                  {change ? (
                    <>
                      <Button size="small" onClick={() => dismiss(r)} aria-label={`Dismiss: ${r.title}`}>
                        Dismiss
                      </Button>
                      <Button
                        size="small"
                        variant="primary"
                        pending={applying}
                        pendingLabel="Applying…"
                        aria-label={`Apply: ${r.title}`}
                        onClick={() =>
                          apply.mutate(r.id, {
                            onSuccess: (res) =>
                              toast.show({ message: `Applied ${res.path}: ${showValue(res.from)} → ${showValue(res.to)}.` }),
                            onError: (e) =>
                              toast.show({ message: e instanceof ApiError ? e.message : "Couldn't apply. Try again." }),
                          })
                        }
                      >
                        Apply
                      </Button>
                    </>
                  ) : (
                    <Button size="small" onClick={() => dismiss(r)} aria-label={`Got it: ${r.title}`}>
                      Got it
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
