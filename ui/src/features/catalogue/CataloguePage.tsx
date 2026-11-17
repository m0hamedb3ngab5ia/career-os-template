import { useQuery } from "@tanstack/react-query";
import { Check, Copy, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Page } from "../../app/PageHeader";
import { apiFetch } from "../../api/client";
import type { Catalogue } from "../../api/types";
import { EmptyState } from "../../kit/EmptyState";
import { filterSections, isCommand, splitCode } from "./filter";
import styles from "./Catalogue.module.css";

/** Route `/catalogue` (REQ-165): everything career-os can do, from docs/CATALOGUE.md. */
export function CataloguePage() {
  const q = useQuery({ queryKey: ["catalogue"], queryFn: () => apiFetch<Catalogue>("/api/catalogue"), staleTime: 5 * 60_000 });
  const [query, setQuery] = useState("");
  const sections = useMemo(() => filterSections(q.data?.sections ?? [], query), [q.data, query]);
  return (
    <Page title="What can I do?" subtitle="Say what you want in Claude Code chat; or use the commands shown. Search by feature or word.">
      <div className={styles.stack}>
        <div role="search" className={styles.search}>
          <Search size={14} strokeWidth={1.7} aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search features, e.g. cover letter"
            aria-label="Search features"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        {q.isError ? (
          <EmptyState title="Couldn’t load the catalogue">{q.error instanceof Error ? q.error.message : "Try again."}</EmptyState>
        ) : q.isPending ? (
          <p className={styles.muted}>Loading…</p>
        ) : sections.length === 0 ? (
          <EmptyState title="No feature matches">Nothing matches “{query.trim()}”. Try a shorter word.</EmptyState>
        ) : (
          sections.map((s) => (
            <section key={s.title} aria-labelledby={`cat-${slug(s.title)}`}>
              <h2 id={`cat-${slug(s.title)}`} className={styles.h2}>{s.title}</h2>
              {s.notes?.length ? (
                <div className={styles.notes}>{s.notes.map((n) => <p key={n} className={styles.what}><Rich text={n} /></p>)}</div>
              ) : null}
              <ul className={styles.rows}>
                {s.rows.map((r) => (
                  <li key={r.feature} className={styles.row}>
                    <div className={styles.name}>{r.feature}</div>
                    <p className={styles.what}><Rich text={r.what} /></p>
                    {r.how ? <How text={r.how} /> : null}
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </Page>
  );
}

const slug = (t: string) => t.toLowerCase().replace(/[^a-z0-9]+/g, "-");

function Rich({ text }: { text: string }) {
  return <>{splitCode(text).map((p, i) => (p.code ? <code key={i} className={styles.code}>{p.text}</code> : <span key={i}>{p.text}</span>))}</>;
}

function How({ text }: { text: string }) {
  return (
    <p className={styles.how}>
      {splitCode(text).map((p, i) =>
        p.code ? (
          <span key={i} className={styles.cmd}>
            <code>{p.text}</code>
            {isCommand(p.text) ? <CopyButton text={p.text} /> : null}
          </span>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </p>
  );
}

function CopyButton({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  async function onCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
    setTimeout(() => setState("idle"), 2000);
  }
  return (
    <button type="button" className={styles.copy} onClick={() => void onCopy()} aria-label={`Copy command: ${text}`}>
      {state === "copied" ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
      <span role="status" className={state === "idle" ? styles.srOnly : undefined}>{state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : "Copy"}</span>
    </button>
  );
}
