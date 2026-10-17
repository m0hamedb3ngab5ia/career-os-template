import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type KeyboardEvent as ReactKeyEvent, type ReactNode, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useBlocker, useNavigate, useParams, useSearchParams } from "react-router";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { useToast } from "../../kit/Toast";
import { errorText } from "../today/api";
import { retryImport, useImport, useProfileWrite, useResumeMeta, useResumes } from "../profile/api";
import { NextButton, NotCarriedOver } from "../profile/ImportPanels";
import { Field, ListInput, Quote } from "./fields";
import { History } from "./History";
import { accept, type Annotation, deleteReply, type Doc, editReply, publish, reject, reopen, reply, useAnnotations, useApplyRun, useAtsText, useDraft, wsKeys } from "./api";
import { useAutosave } from "./useAutosave";
import { cap, type Entry, SKIP, sectionOrder, setAt, spans, targetOrder, targetTexts } from "./doc";
import styles from "./Workspace.module.css";

/** /resumes/:rid — the résumé draft: edit in place, act on suggestions, autosave, Done = one new version. */
export const WorkspacePage = () => <Workspace key={useParams().rid} />;  // new résumé = fresh state

function Workspace() {
  const rid = useParams().rid ?? "";
  const meta = useResumeMeta(rid);
  const draft = useDraft(rid);
  const anns = useAnnotations(rid);
  const save = useAutosave(rid);
  const [doc, setDoc] = useState<Doc | null>(null);
  const [active, setActive] = useState<string | null>(null);  // the focused field's target id
  const [showResolved, setShowResolved] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);  // the selected card's annotation id (wins over `active`)
  // A just-picked card's [annotation id, first field]: once that pick has rendered, scroll its mark (or field) into view.
  const scrollTo = useRef<[string, string] | null>(null);
  useEffect(() => {
    if (!scrollTo.current || scrollTo.current[0] !== picked) return;
    const el = document.getElementById(`t-${scrollTo.current[1]}`);
    scrollTo.current = null;
    if (el) (el.querySelector("mark") ?? el).scrollIntoView?.({ block: "center" });
  });
  const [tab, setTab] = useState<"doc" | "ats">("doc");
  const [history, setHistory] = useState(false);
  // FLOW-001: Next replaces Done while the master is still a draft; ?onboarding=1 forces the first-run flow for testing.
  const row = useResumes().data?.resumes.find((r) => r.rid === rid);
  const onboarding = useSearchParams()[0].get("onboarding") === "1" || (row?.type === "master" && row.status === "draft");
  const ats = useAtsText(rid, tab === "ats");
  const undo = useRef<{ past: Doc[]; future: Doc[]; path: string; at: number }>({ past: [], future: [], path: "", at: 0 });
  const docRef = useRef<Doc | null>(null);
  docRef.current = doc;
  const [accepting, setAccepting] = useState(false);  // an accept is in flight: its reply replaces the doc
  const key = useRef<string | null>(null);
  const qc = useQueryClient();
  const refresh = useCallback(() => void qc.invalidateQueries({ queryKey: wsKeys.annotations(rid) }), [qc, rid]);
  const editor = useRef<HTMLElement>(null);
  const nav = useNavigate();
  const toast = useToast();
  // The unmount flush covers a pending edit; a failed/conflicting one would be lost silently, so ask first.
  const stuck = save.state === "error" || save.state === "conflict";
  const blocker = useBlocker(({ currentLocation, nextLocation }) => stuck && currentLocation.pathname !== nextLocation.pathname);

  useEffect(() => {
    if (draft.data && !draft.isFetching && !doc) {  // wait out the mount refetch: a cached draft has a stale rev
      setDoc(draft.data.resume);
      save.setRev(draft.data.rev);
    }
  }, [draft.data, doc, save]);

  const edit = (path: (string | number)[], value: unknown) => {
    if (!doc) return;
    const u = undo.current, k = path.join("/"), now = Date.now();
    if (k !== u.path || now - u.at > 1000) { u.past.push(doc); if (u.past.length > 100) u.past.shift(); }  // one undo step per burst of typing in one field
    u.path = k; u.at = now; u.future = [];
    let next = setAt(doc, path, value);
    if (path.length === 5 && path[2] === "bullets" && path[4] === "text") {  // DEC-018: an edited bullet is the user's own
      next = setAt(setAt(next, [...path.slice(0, 4), "source"], undefined), [...path.slice(0, 4), "origin"], "user");
    }
    setDoc(next);
    key.current = null;  // the draft changed since the last Done attempt: a new attempt, a new key
    save.schedule(next);
  };

  /** The server's draft replaced ours (accept, reload, revert): local undo steps no longer apply. */
  const resetUndo = () => { undo.current = { past: [], future: [], path: "", at: 0 }; };

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

  const retake = useMutation({
    mutationFn: async (how: "reload" | "overwrite") => {
      if (how === "overwrite") { await save.overwrite(); return; }
      const d = await save.reload();
      setDoc(d.resume);
      key.current = null;
      resetUndo();
    },
  });
  const locked = accepting || done.isPending || retake.isPending;  // no edit may land between the flush and the publish (it would 409 later and be lost) or during an accept

  /*
   * ⌘Z / Ctrl+Z: client-side undo of the user's own edits (DEC-015: a short-lived stack, separate from History).
   * Decision: we handle it everywhere on the page, including inside a focused field. The fields are controlled and
   * autosaved, so the browser's native per-field undo would diverge from the document (it can't restore a value we
   * already saved, and it doesn't reach other fields); one page-wide stack is the consistent behaviour. Native undo
   * is left alone when our stack is empty. Ctrl/⌘+Shift+Z (and Ctrl+Y) redo.
   */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      const z = e.key.toLowerCase() === "z", y = e.key.toLowerCase() === "y" && e.ctrlKey;
      const t = e.target;  // a margin comment/reply field keeps its native undo
      if (t instanceof HTMLElement && t.matches("input,textarea,select,[contenteditable]") && !editor.current?.contains(t)) return;
      if (!mod || e.altKey || !(z || y) || tab !== "doc" || locked) return;
      const u = undo.current, cur = docRef.current;
      const redo = y || e.shiftKey;
      const from = redo ? u.future : u.past, to = redo ? u.past : u.future;
      const next = from.pop();
      if (!next || !cur) return;
      e.preventDefault();
      to.push(cur);
      u.path = ""; u.at = 0;
      key.current = null;
      setDoc(next);
      save.schedule(next);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tab, locked, save]);

  const back = <Link to="/profile#resumes">Back to Profile</Link>;
  const title = meta.data?.name ?? "Résumé";
  const failed = draft.error ?? anns.error;
  if (failed && /no structured version/.test(errorText(failed)))
    return <Page title={title} subtitle={back}><MakeEditable rid={rid} onReady={() => void draft.refetch()} /></Page>;
  if (failed) return <Page title={title} subtitle={back}><p role="alert" className={styles.alert}>Couldn’t load: {errorText(failed)}</p></Page>;
  if (!doc) return <Page title={title} subtitle={back} busy><p className={styles.muted}>Loading…</p></Page>;

  const open = (anns.data ?? []).filter((a) => a.status === "open");
  const order = targetOrder(doc);
  const pos = (a: Annotation) => { const i = order.indexOf(a.target_id ?? ""); return i < 0 ? order.length : i; };
  const resolved = (anns.data ?? []).filter((a) => a.status === "rejected" || a.status === "accepted");
  const cards = (showResolved ? [...open, ...resolved] : open).sort((a, b) => pos(a) - pos(b));
  const onTarget = (id: string) => open.filter((a) => a.target_id === id);
  const texts = targetTexts(doc);
  /** [field, quote to mark inline | null = whole field] a card points at: each anchor's target (inline when its quote
   * is still there), else (bridged feedback items have no target) every field holding its quote. */
  const hits = (a: Annotation): [string, string | null][] => {
    const q = quoteOf(a);
    if (a.target_id) {
      return anchorsOf(a).map(({ target_id: id, quote }) => {
        const t = texts.find(([f]) => f === id)?.[1] ?? "";
        return [id, quote && spans(t, quote).length ? quote : null];
      });
    }
    return q ? texts.filter(([, t]) => spans(t, q).length).map(([id]) => [id, q]) : [];
  };
  const sel = (anns.data ?? []).find((a) => a.id === picked);
  // field -> quotes to mark inline; an empty list = highlight the whole field
  const lit = new Map<string, string[]>();
  for (const [id, q] of sel ? hits(sel) : active ? [[active, null] as [string, null]] : []) {
    lit.set(id, [...(lit.get(id) ?? []), ...(q ? [q] : [])]);
  }
  // Every open comment's passages, Docs-style: quoted words get a faint inline mark; only a passage with no quote
  // (whole-field comment, stale quote) tints the whole field.
  const faint = new Map<string, string[]>();
  const whole = new Set<string>();
  for (const a of open) for (const [id, q] of hits(a)) {
    if (q) faint.set(id, [...(faint.get(id) ?? []), q]); else whole.add(id);
  }
  /** Select a card (toggle unless `keep`): highlight its passages and scroll the first into view (after render). */
  const pick = (a: Annotation, keep = false) => {
    if (picked === a.id) { if (!keep) setPicked(null); return; }
    setPicked(a.id);
    const first = hits(a)[0]?.[0];
    if (!keep && first) scrollTo.current = [a.id, first];
  };

  /** A field the annotations can point at: highlight, inline suggestion preview, focus pairs it with its card. */
  const target = (id: string, child: ReactNode) => {
    const here = onTarget(id);
    const sugg = here.find((a) => a.kind === "suggestion" && a.proposed);
    return (
      <div id={`t-${id}`} className={styles.target} data-marked={whole.has(id) || undefined} data-on={(lit.has(id) && !lit.get(id)!.length) || undefined}
        onFocus={() => { setActive(id); setPicked(null); }}>
        <Quote.Provider value={{ on: lit.get(id) ?? NONE, faint: faint.get(id) ?? NONE, sugg: sugg ? { base: String(sugg.base ?? ""), proposed: sugg.proposed! } : undefined }}>{child}</Quote.Provider>
      </div>
    );
  };
  const field = (label: string, path: (string | number)[], value: unknown, multi = false) =>
    <Field label={label} locked={locked} multi={multi} value={String(value ?? "")} onChange={(v) => edit(path, v)} />;

  /** One entry key: text, string list (stack, coursework, activities) or links [{label, url}]. */
  const entryField = (t: string, i: number, k: string, v: unknown): ReactNode => {
    const label = `${cap(t)} ${i + 1} ${k}`;
    if (typeof v === "string") return <span key={k}>{field(label, [t, i, k], v)}</span>;
    if (Array.isArray(v) && v.every((x) => typeof x === "string"))
      return <span key={k}><ListInput label={label} value={v as string[]} locked={locked} onChange={(a) => edit([t, i, k], a)} /></span>;
    if (k === "links" && Array.isArray(v))
      return (v as { label?: string; url?: string }[]).map((l, n) => (
        <span key={`${k}${n}`}>{field(`${cap(t)} ${i + 1} link ${n + 1} label`, [t, i, k, n, "label"], l.label)}{field(`${cap(t)} ${i + 1} link ${n + 1} url`, [t, i, k, n, "url"], l.url)}</span>
      ));
    return null;
  };

  const identity = (doc.identity as Record<string, unknown> | undefined) ?? {};
  const status = save.state === "conflict"
    ? <span role="alert" className={styles.alert}>This draft changed elsewhere. Reload takes the saved version (drops your edits); Overwrite keeps yours.{" "}
        <Button size="small" disabled={retake.isPending} onClick={() => retake.mutate("reload")}>Reload</Button>{" "}
        <Button size="small" disabled={retake.isPending} onClick={() => retake.mutate("overwrite")}>Overwrite</Button>
        {retake.isError ? <> {errorText(retake.error)}</> : null}</span>
    : save.state === "error"
    ? <span role="alert" className={styles.alert}>Couldn’t save: {save.error} <Button size="small" onClick={() => void save.flush()}>Retry save</Button></span>
    : <span className={styles.muted} aria-live="polite">{save.state === "saving" ? "Saving…" : "All changes saved"}</span>;

  return (
    <Page title={title} subtitle={<>{back} · {status} · <span className={styles.muted}>{open.length ? `${open.length} open suggestion${open.length === 1 ? "" : "s"}` : "All handled"}</span></>}
      actions={<><Button disabled={tab !== "doc"} onClick={() => setHistory((h) => !h)} aria-pressed={history}>↶ History</Button>{" "}{onboarding
        ? <NextButton rid={rid} flush={save.flush} onDone={() => void nav("/profile/answers")} />
        : <Button variant="primary" pending={done.isPending} pendingLabel="Saving…" disabled={accepting} onClick={() => done.mutate()}>Done</Button>}</>}>
      {blocker.state === "blocked" ? (
        <p role="alert" className={styles.alert}>Your latest edits aren’t saved. Leave anyway?{" "}
          <Button size="small" onClick={() => blocker.proceed()}>Leave anyway</Button>{" "}
          <Button size="small" onClick={() => blocker.reset()}>Stay</Button></p>
      ) : null}
      {done.isError ? <p role="alert" className={styles.alert}>Couldn’t finish: {errorText(done.error)}. Press Done to try again.</p> : null}
      <div role="tablist" aria-label="Document tabs" className={styles.tabs}>
        {([["doc", "Résumé"], ["ats", "ATS view"]] as const).map(([t, l]) => {
          const go = async (to: "doc" | "ats") => {
            if (to === "ats" && !(await save.flush())) return false;  // a failed save keeps the current tab; its error is already shown
            setTab(to);
            return true;
          };
          const onKeyDown = (e: ReactKeyEvent) => {
            if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
            e.preventDefault();
            const to = t === "doc" ? "ats" : "doc";
            void go(to).then((ok) => ok && document.getElementById(`tab-${to}`)?.focus());
          };
          return (
            <Button key={t} id={`tab-${t}`} role="tab" aria-selected={tab === t} aria-controls={`tabpanel-${t}`} tabIndex={tab === t ? 0 : -1}
              className={styles.tab} onKeyDown={onKeyDown} onClick={() => void go(t)}>{l}</Button>
          );
        })}
      </div>
      {tab === "ats" ? (ats.isError
        ? <p id="tabpanel-ats" role="alert" className={styles.alert}>Couldn’t load the ATS view: {errorText(ats.error)}</p>
        : <pre id="tabpanel-ats" role="tabpanel" aria-labelledby="tab-ats" className={styles.ats} tabIndex={0}>{ats.data ?? "Loading…"}</pre>) : (
      <div id="tabpanel-doc" role="tabpanel" aria-labelledby="tab-doc" className={styles.app}>
        <article ref={editor} className={styles.page} aria-label="Résumé draft">
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
                ? skillRows(doc).map(({ label, path, items }) => (
                    <p key={label} className={styles.row}><span className={styles.muted}>{cap(label)}:</span>
                      <ListInput label={`Skills ${label}`} value={items} locked={locked} onChange={(a) => edit(path, a)} /></p>
                  ))
                : (doc[t] as Entry[]).map((e, i) => (
                    <div key={e.id ?? i} className={styles.entry}>
                      <div className={styles.row}>
                        {Object.entries(e).filter(([k]) => !SKIP.has(k)).map(([k, v]) => entryField(t, i, k, v))}
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
        {history
          ? <History rid={rid} flush={save.flush} lock={setAccepting} onClose={() => setHistory(false)}
              onReverted={(d) => { setDoc(d.resume); save.setRev(d.rev); key.current = null; resetUndo(); }} />
          : <Margin rid={rid} cards={cards} resolvedCount={resolved.length} showResolved={showResolved} onToggleResolved={() => setShowResolved((v) => !v)} on={(a) => (sel ? sel.id === a.id : active !== null && active === a.target_id)} pick={pick}
              onAccepted={(d) => { setDoc(d.resume); save.setRev(d.rev); key.current = null; resetUndo(); }} flush={save.flush} lock={setAccepting}
              refresh={refresh} />}
      </div>)}
      <NotCarriedOver rid={rid} flush={save.flush} onRestored={() => retake.mutate("reload")} />
    </Page>
  );
}

/** The words a card is anchored on: its `quote`, or a bridged feedback item's quote (`base`, no target). */
const quoteOf = (a: Annotation): string | null => a.quote ?? (a.target_id ? null : a.base) ?? null;
/** Every passage a card points at: its `anchors` (a comment on several passages), else its one target + quote. */
const anchorsOf = (a: Annotation): { target_id: string; quote: string | null }[] =>
  a.anchors?.length ? a.anchors.map((x) => ({ target_id: x.target_id, quote: x.quote ?? null }))
    : a.target_id ? [{ target_id: a.target_id, quote: quoteOf(a) }] : [];
/** The quotes a card lists (first 3 shown, the rest counted). */
const quotesOf = (a: Annotation): string[] => {
  const qs = anchorsOf(a).map((x) => x.quote).filter((q): q is string => !!q);
  const q = quoteOf(a);
  return qs.length ? qs : q ? [q] : [];
};
const NONE: readonly string[] = [];
const SHOWN = 3;

interface MarginProps {
  rid: string;
  cards: Annotation[];
  resolvedCount: number;
  showResolved: boolean;
  onToggleResolved: () => void;
  on: (a: Annotation) => boolean;
  pick: (a: Annotation, keep?: boolean) => void;
  onAccepted: (d: { rev: number; resume: Doc }) => void;
  flush: () => Promise<boolean>;
  lock: (b: boolean) => void;
  refresh: () => void;
}

/** Margin cards, each placed level with its target (pushed down to avoid overlap); stacked on narrow screens. */
function Margin({ rid, cards, resolvedCount, showResolved, onToggleResolved, on, pick, onAccepted, flush, lock, refresh }: MarginProps) {
  const ref = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    const aside = ref.current;
    if (!aside) return;
    const place = () => {
      if (getComputedStyle(aside).position !== "relative") return;
      const base = aside.getBoundingClientRect().top;
      // Stack in document order (not creation order), else a card aligned low leaves a gap above later, higher ones.
      const items = (Array.from(aside.children) as HTMLElement[]).map((el, i) => {
        const t = document.getElementById(`t-${el.dataset.for}`);
        return { el, i, want: t ? t.getBoundingClientRect().top - base : Infinity };
      }).sort((x, y) => x.want - y.want || x.i - y.i);
      let bottom = 0;
      for (const { el, want } of items) {
        const top = Math.max(want === Infinity ? bottom : want, bottom);
        el.style.top = `${top}px`;
        bottom = top + el.offsetHeight + 8;
      }
      aside.style.minHeight = `${bottom}px`;
    };
    place();
    // The text reflows without a React render (fields auto-size, fonts load, window resizes): re-place then too.
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(place);
    const page = aside.parentElement?.parentElement;
    if (page) ro.observe(page);
    for (const el of Array.from(aside.children)) ro.observe(el);
    return () => ro.disconnect();
  });
  return (
    <div>
      {resolvedCount ? (
        <Button size="small" className={styles.resolvedToggle} aria-pressed={showResolved} onClick={onToggleResolved}>
          {showResolved ? "Hide" : "Show"} resolved ({resolvedCount})
        </Button>
      ) : null}
      <aside ref={ref} className={styles.margin} aria-label="Suggestions">
        {cards.map((a) => a.status === "open"
          ? <Card key={a.id} rid={rid} a={a} on={on(a)} pick={pick} onAccepted={onAccepted} flush={flush} lock={lock} refresh={refresh}
              waiting={cards.filter((k) => k.parent === a.id && k.status === "open").length} />
          : <ResolvedCard key={a.id} rid={rid} a={a} on={on(a)} pick={pick} refresh={refresh} />)}
      </aside>
    </div>
  );
}

/** A rejected/accepted card: muted and read-only. A resolved one can be reopened; an accepted one is reverted in History. */
/** How a decided item ended (server `resolution`); legacy rejected items carry none. */
const OUTCOME: Record<string, string> = { applied: "Applied", edited: "Fixed by you", dismissed: "Dismissed" };
const outcome = (a: Annotation) => OUTCOME[a.resolution ?? (a.status === "accepted" ? "applied" : "")] ?? "Resolved";

function ResolvedCard({ rid, a, on, pick, refresh }: { rid: string; a: Annotation; on: boolean; pick: (a: Annotation, keep?: boolean) => void; refresh: () => void }) {
  const undo = useMutation({ mutationFn: () => reopen(rid, a.id), onSettled: refresh });
  const who = a.author === "ai" ? "Claude" : "You";
  const tid = `card-${a.id}`;
  return (
    <article className={styles.card} data-resolved data-on={on || undefined} data-for={a.target_id ?? ""} aria-labelledby={tid}
      onClick={(e) => { if (!(e.target as Element).closest("button")) pick(a); }}>
      <p className={styles.muted}>{a.kind === "suggestion" ? `${who} suggested` : `${who} commented`} · <b>{outcome(a)}</b></p>
      {quotesOf(a).slice(0, SHOWN).map((q, i) => <p key={i} className={styles.quote}>“{q}”</p>)}
      <button type="button" id={tid} className={styles.pick} aria-pressed={on} onClick={() => pick(a)}>{a.text}</button>
      {(a.replies ?? []).map((r, i) => (
        <p key={i} className={styles.reply}><b>{r.author === "ai" ? "Claude" : "You"}:</b> {String(r.text ?? "")}</p>
      ))}
      {a.status === "rejected" ? <div className={styles.actions}><span className={styles.grow} /><Button size="small" disabled={undo.isPending} onClick={() => undo.mutate()}>Reopen</Button></div> : null}
      {undo.isError ? <p role="alert" className={styles.alert}>{errorText(undo.error)}</p> : null}
    </article>
  );
}

/** One reply. The user's own, not yet picked up by an Apply-comment run (and with an id), can be edited or deleted. */
function ReplyRow({ rid, aid, r, refresh }: { rid: string; aid: string; r: Record<string, unknown>; refresh: () => void }) {
  const [mode, setMode] = useState<"view" | "edit" | "confirm">("view");
  const [text, setText] = useState("");
  const id = typeof r.id === "string" ? r.id : "";
  const mine = r.author === "user" && id !== "";
  const save = useMutation({ mutationFn: () => editReply(rid, aid, id, text.trim()), onSuccess: () => setMode("view"), onSettled: refresh });
  const del = useMutation({ mutationFn: () => deleteReply(rid, aid, id), onSettled: refresh });
  const busy = save.isPending || del.isPending;
  const who = <b>{r.author === "ai" ? "Claude" : "You"}:</b>;
  if (!mine) return <p className={styles.reply}>{who} {String(r.text ?? "")}</p>;
  if (r.picked_up) return <p className={styles.reply}>{who} {String(r.text ?? "")} <span className={styles.muted}>· Claude has picked this up</span></p>;
  const err = save.isError ? save.error : del.isError ? del.error : null;
  return (
    <div className={styles.reply}>
      {mode === "edit" ? (
        <form className={styles.replyForm} onSubmit={(e) => { e.preventDefault(); if (text.trim() && !busy) save.mutate(); }}>
          <input aria-label="Edit reply" className={styles.input} value={text} autoFocus onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); setMode("view"); } }} />
          <div className={styles.actions}>
            <Button type="submit" size="small" disabled={!text.trim() || busy}>Save</Button>
            <Button size="small" disabled={busy} onClick={() => setMode("view")}>Cancel</Button>
          </div>
        </form>
      ) : (
        <>
          <p>{who} {String(r.text ?? "")}</p>
          <div className={styles.actions}>
            {mode === "confirm" ? (
              <>
                <span className={styles.muted}>Delete this reply?</span>
                <Button size="small" disabled={busy} onClick={() => del.mutate()}>Delete</Button>
                <Button size="small" disabled={busy} onClick={() => setMode("view")}>Keep</Button>
              </>
            ) : (
              <>
                <Button size="small" onClick={() => { setText(String(r.text ?? "")); save.reset(); setMode("edit"); }}>Edit</Button>
                <Button size="small" onClick={() => { del.reset(); setMode("confirm"); }}>Delete</Button>
              </>
            )}
          </div>
        </>
      )}
      {err ? <p role="alert" className={styles.alert}>{errorText(err)}</p> : null}
    </div>
  );
}

/** `waiting`: this comment's open child suggestions (from an earlier Apply); it resolves itself once they're decided. */
function Card({ rid, a, on, pick, onAccepted, flush, lock, refresh, waiting = 0 }: Omit<MarginProps, "cards" | "on" | "resolvedCount" | "showResolved" | "onToggleResolved"> & { a: Annotation; on: boolean; waiting?: number }) {
  const [text, setText] = useState("");
  const [failed, setFailed] = useState("");
  const [runId, setRunId] = useState<string | null>(null);  // the Apply re-draft run being followed
  const follow = useApplyRun(rid, runId);
  useEffect(() => { if (follow.ended) refresh(); }, [follow.ended, refresh]);  // its suggestions/replies show up
  const sent = useRef("");  // the text actually submitted: the input may change while the send is pending  // reply text whose send failed: the reply may exist server-side, so no resend until edited
  const act = useMutation({
    mutationFn: async (what: "accept" | "reject" | "reply" | "apply") => {
      if (what === "accept") {
        lock(true);  // typing during the request would be overwritten by the accepted doc
        try {
          if (!(await flush())) throw new Error("Save your changes first (Retry save).");
          onAccepted(await accept(rid, a.id));
        } finally { lock(false); }
      } else if (what === "reject") await reject(rid, a.id);
      else {
        const r = await reply(rid, a.id, text.trim(), what === "apply");  // Apply: unsent reply text = instructions
        if (r.run_id) setRunId(r.run_id);
        setText("");
      }
    },
    onError: (_e, what) => { if (what !== "accept" && what !== "reject") setFailed(sent.current); },
    onSettled: refresh,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim() && text.trim() !== failed && !act.isPending) { sent.current = text.trim(); act.mutate("reply"); }  // Enter bypasses the disabled button
  };
  const who = a.author === "ai" ? "Claude" : "You";
  const tid = `card-${a.id}`;
  return (
    <article className={styles.card} data-on={on || undefined} data-for={a.target_id ?? ""} aria-labelledby={tid}
      onFocus={(e) => { if ((e.target as Element).closest("form")) pick(a, true); }}
      onClick={(e) => { if (!(e.target as Element).closest("form, button")) pick(a); }}>
      <p className={styles.muted}>{a.kind === "suggestion" ? `${who} suggests` : `${who} commented`}</p>
      {quotesOf(a).slice(0, SHOWN).map((q, i) => <p key={i} className={styles.quote}>“{q}”</p>)}
      {quotesOf(a).length > SHOWN ? <p className={styles.muted}>+{quotesOf(a).length - SHOWN} more</p> : null}
      <button type="button" id={tid} className={styles.pick} aria-pressed={on} onClick={() => pick(a)}>{a.text}</button>
      {(a.replies ?? []).map((r, i) => <ReplyRow key={String(r.id ?? i)} rid={rid} aid={a.id} r={r} refresh={refresh} />)}
      {runId && !follow.ended ? <p className={styles.muted} role="status">Claude is revising…</p> : null}
      {runId && follow.ended && follow.failed ? <p role="alert" className={styles.alert}>Claude couldn’t revise this: {follow.error}. Your comment is saved.</p> : null}
      {runId && follow.ended && !follow.failed && follow.written ? <p className={styles.muted} role="status">Claude added {follow.written.length} {follow.written.length === 1 ? "response" : "responses"}.</p> : null}
      {waiting ? <p className={styles.muted}>{waiting} suggestion{waiting === 1 ? "" : "s"} to review</p> : null}
      <form className={styles.replyForm} onSubmit={submit}>
        <input aria-label="Reply" placeholder="Reply…" className={styles.input} value={text} onChange={(e) => setText(e.target.value)} />
        <div className={styles.actions}>
          <Button type="submit" size="small" disabled={!text.trim() || text.trim() === failed || act.isPending}>Send</Button>
          <span className={styles.grow} />
          {a.kind === "suggestion" ? (
            <>
              <Button size="small" variant="primary" disabled={act.isPending} onClick={() => act.mutate("accept")}>Accept</Button>
              <Button size="small" disabled={act.isPending} onClick={() => act.mutate("reject")}>Reject</Button>
            </>
          ) : (
            <>
              <Button size="small" variant="primary" disabled={act.isPending || waiting > 0 || (!!runId && !follow.ended)}
                title="Claude turns this comment into suggestions you accept or reject; reply text above goes along as instructions"
                onClick={() => { sent.current = text.trim(); act.mutate("apply"); }}>Apply</Button>
              <Button size="small" disabled={act.isPending} title="Mark done: you fixed it yourself, or it doesn't apply" onClick={() => act.mutate("reject")}>Resolve</Button>
            </>
          )}
        </div>
      </form>
      {act.isError ? <p role="alert" className={styles.alert}>{errorText(act.error)}</p> : null}
    </article>
  );
}

/** Skills rows: `skill_groups` [{label, items}] replaces the `skills` map when present (schema). */
function skillRows(doc: Doc): { label: string; path: (string | number)[]; items: string[] }[] {
  const groups = doc.skill_groups as { label?: string; items?: string[] }[] | undefined;
  if (groups?.length) return groups.map((g, i) => ({ label: g.label ?? `group ${i + 1}`, path: ["skill_groups", i, "items"], items: g.items ?? [] }));
  return Object.entries((doc.skills as Record<string, string[]>) ?? {}).map(([k, v]) => ({ label: k, path: ["skills", k], items: v }));
}

/** An upload from before the editor has no structured version yet: run the import (DEC-019), then load the draft. */
function MakeEditable({ rid, onReady }: { rid: string; onReady: () => void }) {
  const start = useProfileWrite(retryImport);
  const imp = useImport(rid);
  const refetchImport = imp.refetch;
  // ponytail: re-asks for the draft and the import state every 3 s while the import runs; fine for a one-minute run
  useEffect(() => {
    if (!start.isSuccess) return;
    const t = window.setInterval(() => { onReady(); void refetchImport(); }, 3000);
    return () => window.clearInterval(t);
  }, [start.isSuccess, onReady, refetchImport]);
  const failed = start.isSuccess && imp.data?.state === "failed" && imp.dataUpdatedAt > start.submittedAt;
  if (start.isSuccess && !failed) return <p role="status" className={styles.muted}>Making this résumé editable… this takes about a minute.</p>;
  return (
    <p className={styles.muted}>
      This résumé was uploaded before the editor existed, so it has no editable version yet.{" "}
      <Button size="small" variant="primary" pending={start.isPending} pendingLabel="Starting…" onClick={() => start.mutate(rid)}>{failed ? "Try again" : "Make editable"}</Button>
      {start.isError ? <span role="alert" className={styles.alert}> {errorText(start.error)}</span> : null}
      {failed ? <span role="alert" className={styles.alert}> Couldn’t make it editable{imp.data?.reason ? `: ${imp.data.reason}` : ""}.</span> : null}
    </p>
  );
}
