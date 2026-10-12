import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { useToast } from "../../kit/Toast";
import { errorText } from "../today/api";
import { useResumeMeta } from "../profile/api";
import { accept, type Annotation, type Doc, publish, reject, reply, useAnnotations, useDraft, wsKeys } from "./api";
import { useAutosave } from "./useAutosave";
import styles from "./Workspace.module.css";

const ENTRY_SECTIONS = ["experience", "projects", "leadership", "education"];
const SKIP = new Set(["id", "source", "origin"]);
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
type Entry = Record<string, unknown> & { id?: string; bullets?: { id?: string; text?: string }[] };

/** Copy of `doc` with the value at `path` replaced. */
function setAt(doc: Doc, path: (string | number)[], value: unknown): Doc {
  const out = structuredClone(doc);
  let node = out as Record<string | number, unknown>;
  for (const k of path.slice(0, -1)) node = node[k] as Record<string | number, unknown>;
  node[path[path.length - 1]!] = value;
  return out;
}

/** Section types in the résumé's own order (`sections[].order`), entry sections and skills only. */
function sectionOrder(doc: Doc): string[] {
  const secs = ((doc.sections as { type: string; order?: number }[] | undefined) ?? []).slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const types = secs.map((s) => s.type);
  for (const t of [...ENTRY_SECTIONS, "skills"]) if (doc[t] && !types.includes(t)) types.push(t);
  return types.filter((t) => [...ENTRY_SECTIONS, "skills"].includes(t) && doc[t]);
}

/** Annotation targets in document order: summary, then every bullet. Cards follow this order. */
function targetOrder(doc: Doc): string[] {
  const ids = ["summary"];
  for (const t of sectionOrder(doc)) for (const e of (ENTRY_SECTIONS.includes(t) ? (doc[t] as Entry[]) : [])) for (const b of e.bullets ?? []) if (b.id) ids.push(b.id);
  return ids;
}

/** /resumes/:rid — the résumé draft: edit in place, act on suggestions, autosave, Done = one new version. */
export const WorkspacePage = () => <Workspace key={useParams().rid} />;  // new résumé = fresh state

function Workspace() {
  const rid = useParams().rid ?? "";
  const meta = useResumeMeta(rid);
  const draft = useDraft(rid);
  const anns = useAnnotations(rid);
  const save = useAutosave(rid);
  const [doc, setDoc] = useState<Doc | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);  // read-only while an accept is in flight: its reply replaces the doc
  const key = useRef<string | null>(null);
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();

  useEffect(() => {
    if (draft.data && !draft.isFetching && !doc) {  // wait out the mount refetch: a cached draft has a stale rev
      setDoc(draft.data.resume);
      save.setRev(draft.data.rev);
    }
  }, [draft.data, doc, save]);

  const edit = (path: (string | number)[], value: unknown) => {
    if (!doc) return;
    const next = setAt(doc, path, value);
    setDoc(next);
    key.current = null;  // the draft changed since the last Done attempt: a new attempt, a new key
    save.schedule(next);
  };

  const done = useMutation({
    mutationFn: async () => {
      if (!(await save.flush())) throw new Error("Save your changes first (Retry save).");
      key.current ??= crypto.randomUUID();
      return publish(rid, key.current);
    },
    onSuccess: (p) => {
      key.current = null;
      toast.show({ message: `Saved as version ${p.n}` });
      void nav("/profile#resumes");
    },
  });

  const back = <Link to="/profile#resumes">Back to Profile</Link>;
  const title = meta.data?.name ?? "Résumé";
  const failed = draft.error ?? anns.error;
  if (failed) return <Page title={title} subtitle={back}><p role="alert" className={styles.alert}>Couldn’t load: {errorText(failed)}</p></Page>;
  if (!doc) return <Page title={title} subtitle={back} busy><p className={styles.muted}>Loading…</p></Page>;

  const open = (anns.data ?? []).filter((a) => a.status === "open");
  const order = targetOrder(doc);
  const pos = (a: Annotation) => { const i = order.indexOf(a.target_id ?? ""); return i < 0 ? order.length : i; };
  const cards = open.slice().sort((a, b) => pos(a) - pos(b));
  const onTarget = (id: string) => open.filter((a) => a.target_id === id);

  /** A field the annotations can point at: highlight, inline suggestion preview, focus pairs it with its card. */
  const target = (id: string, child: ReactNode) => {
    const here = onTarget(id);
    const sugg = here.find((a) => a.kind === "suggestion" && a.proposed);
    return (
      <div id={`t-${id}`} className={styles.target} data-marked={here.length > 0 || undefined} data-on={active === id || undefined}
        onFocus={() => setActive(id)}>
        {child}
        {sugg ? <p className={styles.sugg}><del>{sugg.base}</del> <ins>{sugg.proposed}</ins></p> : null}
      </div>
    );
  };
  const field = (label: string, path: (string | number)[], value: unknown, multi = false) =>
    multi
      ? <textarea aria-label={label} readOnly={locked} className={styles.field} rows={1} value={String(value ?? "")} onChange={(e) => edit(path, e.target.value)} />
      : <input aria-label={label} readOnly={locked} className={styles.field} value={String(value ?? "")} onChange={(e) => edit(path, e.target.value)} />;

  const identity = (doc.identity as Record<string, unknown> | undefined) ?? {};
  const status = save.state === "error"
    ? <span role="alert" className={styles.alert}>Couldn’t save: {save.error} <Button size="small" onClick={() => void save.flush()}>Retry save</Button></span>
    : <span className={styles.muted} aria-live="polite">{save.state === "saving" ? "Saving…" : "All changes saved"}</span>;

  return (
    <Page title={title} subtitle={<>{back} · {status}</>}
      actions={<Button variant="primary" pending={done.isPending} pendingLabel="Saving…" onClick={() => done.mutate()}>Done</Button>}>
      {done.isError ? <p role="alert" className={styles.alert}>Couldn’t finish: {errorText(done.error)}. Press Done to try again.</p> : null}
      <div className={styles.app}>
        <article className={styles.page} aria-label="Résumé draft">
          <div className={styles.name}>{field("Name", ["identity", "name"], identity.name)}</div>
          <div className={styles.contact}>
            {Object.entries(identity).filter(([k, v]) => k !== "name" && typeof v === "string").map(([k, v]) => (
              <span key={k}>{field(cap(k), ["identity", k], v)}</span>
            ))}
          </div>
          {"summary" in doc ? target("summary", field("Summary", ["summary"], doc.summary, true)) : null}
          {sectionOrder(doc).map((t) => (
            <section key={t} aria-labelledby={`h-${t}`}>
              <h2 id={`h-${t}`} className={styles.h2}>{cap(t)}</h2>
              {t === "skills"
                ? Object.entries(doc.skills as Record<string, string[]>).map(([k, v]) => (
                    <p key={k} className={styles.row}><span className={styles.muted}>{cap(k)}:</span>
                      <SkillsInput label={`Skills ${k}`} value={v} locked={locked} onChange={(a) => edit(["skills", k], a)} /></p>
                  ))
                : (doc[t] as Entry[]).map((e, i) => (
                    <div key={e.id ?? i} className={styles.entry}>
                      <div className={styles.row}>
                        {Object.entries(e).filter(([k, v]) => !SKIP.has(k) && typeof v === "string").map(([k, v]) => (
                          <span key={k}>{field(`${cap(t)} ${i + 1} ${k}`, [t, i, k], v)}</span>
                        ))}
                      </div>
                      <ul className={styles.bullets}>
                        {(e.bullets ?? []).map((b, j) => (
                          <li key={b.id ?? j}>{target(b.id ?? `${t}-${i}-${j}`, field(`${cap(t)} ${i + 1} bullet ${j + 1}`, [t, i, "bullets", j, "text"], b.text, true))}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
            </section>
          ))}
        </article>
        <Margin rid={rid} cards={cards} active={active} setActive={setActive}
          onAccepted={(d) => { setDoc(d.resume); save.setRev(d.rev); key.current = null; }} flush={save.flush} lock={setLocked}
          refresh={() => void qc.invalidateQueries({ queryKey: wsKeys.annotations(rid) })} />
      </div>
    </Page>
  );
}

interface MarginProps {
  rid: string;
  cards: Annotation[];
  active: string | null;
  setActive: (id: string) => void;
  onAccepted: (d: { rev: number; resume: Doc }) => void;
  flush: () => Promise<boolean>;
  lock: (b: boolean) => void;
  refresh: () => void;
}

/** Skills group: comma-separated text, stored as string[] (kept as typed so "a, " isn't eaten). */
function SkillsInput({ label, value, locked, onChange }: { label: string; value: string[]; locked: boolean; onChange: (a: string[]) => void }) {
  const [text, setText] = useState(value.join(", "));
  return <input aria-label={label} readOnly={locked} className={styles.field} value={text}
    onChange={(e) => { setText(e.target.value); onChange(e.target.value.split(",").map((x) => x.trim()).filter(Boolean)); }} />;
}

/** Margin cards, each placed level with its target (pushed down to avoid overlap); stacked on narrow screens. */
function Margin({ rid, cards, active, setActive, onAccepted, flush, lock, refresh }: MarginProps) {
  const ref = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    const aside = ref.current;
    if (!aside || getComputedStyle(aside).position !== "relative") return;
    let bottom = 0;
    for (const el of Array.from(aside.children) as HTMLElement[]) {
      const t = document.getElementById(`t-${el.dataset.for}`);
      const want = t ? t.getBoundingClientRect().top - aside.getBoundingClientRect().top : bottom;
      const top = Math.max(want, bottom);
      el.style.top = `${top}px`;
      bottom = top + el.offsetHeight + 8;
    }
    aside.style.minHeight = `${bottom}px`;
  });
  return (
    <aside ref={ref} className={styles.margin} aria-label="Suggestions">
      {cards.map((a) => <Card key={a.id} rid={rid} a={a} on={active === a.target_id} setActive={setActive}
        onAccepted={onAccepted} flush={flush} lock={lock} refresh={refresh} />)}
    </aside>
  );
}

function Card({ rid, a, on, setActive, onAccepted, flush, lock, refresh }: Omit<MarginProps, "cards" | "active"> & { a: Annotation; on: boolean }) {
  const [text, setText] = useState("");
  const [apply, setApply] = useState(false);
  const act = useMutation({
    mutationFn: async (what: "accept" | "reject" | "reply") => {
      if (what === "accept") {
        lock(true);  // typing during the request would be overwritten by the accepted doc
        try {
          if (!(await flush())) throw new Error("Save your changes first (Retry save).");
          onAccepted(await accept(rid, a.id));
        } finally { lock(false); }
      } else if (what === "reject") await reject(rid, a.id);
      else {
        await reply(rid, a.id, text.trim(), apply);
        setText("");
        setApply(false);
      }
    },
    onSettled: refresh,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim() && !act.isPending) act.mutate("reply");  // Enter bypasses the disabled button
  };
  const who = a.author === "ai" ? "Claude" : "You";
  const tid = `card-${a.id}`;
  return (
    <article className={styles.card} data-on={on || undefined} data-for={a.target_id ?? ""} aria-labelledby={tid}
      onFocus={() => a.target_id && setActive(a.target_id)}>
      <p className={styles.muted}>{a.kind === "suggestion" ? `${who} suggests` : `${who} commented`}</p>
      <p id={tid}>{a.text}</p>
      {(a.replies ?? []).map((r, i) => (
        <p key={i} className={styles.reply}><b>{r.author === "ai" ? "Claude" : "You"}:</b> {String(r.text ?? "")}</p>
      ))}
      <form className={styles.replyForm} onSubmit={submit}>
        <input aria-label="Reply" placeholder="Reply…" className={styles.input} value={text} onChange={(e) => setText(e.target.value)} />
        <label className={styles.muted}><input type="checkbox" checked={apply} onChange={(e) => setApply(e.target.checked)} /> Apply comment (Claude revises this)</label>
        <div className={styles.actions}>
          <Button type="submit" size="small" disabled={!text.trim() || act.isPending}>Send</Button>
          <span className={styles.grow} />
          {a.kind === "suggestion" ? (
            <>
              <Button size="small" variant="primary" disabled={act.isPending} onClick={() => act.mutate("accept")}>Accept</Button>
              <Button size="small" disabled={act.isPending} onClick={() => act.mutate("reject")}>Reject</Button>
            </>
          ) : <Button size="small" disabled={act.isPending} onClick={() => act.mutate("reject")}>Resolve</Button>}
        </div>
      </form>
      {act.isError ? <p role="alert" className={styles.alert}>{errorText(act.error)}</p> : null}
    </article>
  );
}
