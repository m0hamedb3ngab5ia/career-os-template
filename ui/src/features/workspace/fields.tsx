import { createContext, type ReactNode, useContext, useLayoutEffect, useRef, useState } from "react";
import { spansOf } from "./doc";
import styles from "./Workspace.module.css";

/** Firefox/Safari lack CSS `field-sizing: content`; there JS sizes the field instead (feature-detected once). */
const nativeSizing = typeof CSS !== "undefined" && typeof CSS.supports === "function" && CSS.supports("field-sizing", "content");

interface FieldProps { label: string; value: string; locked: boolean; multi?: boolean; onChange: (v: string) => void }

/** A document-looking text field: textarea grows with its text, input with its width. */
export function Field({ label, value, locked, multi, onChange }: FieldProps) {
  const ref = useRef<HTMLTextAreaElement & HTMLInputElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (nativeSizing || !el) return;
    if (multi) { el.style.height = "auto"; el.style.height = `${el.scrollHeight}px`; }
    else el.size = Math.max(value.length + 1, 4);
  });
  const common = { "aria-label": label, readOnly: locked, className: styles.field, value, ref };
  const control = multi
    ? <textarea {...common} rows={1} onChange={(e) => onChange(e.target.value)} />
    : <input {...common} onChange={(e) => onChange(e.target.value)} />;
  const hit = spansOf(value, useContext(Quote));
  if (!hit.length) return control;
  // Text sits in a native textarea/input (editing, caret, IME stay native), which can't style a range. So a mirror
  // with the same box and font renders the text transparent behind it, with <mark> over the quoted words.
  const parts: ReactNode[] = [];
  let at = 0;
  for (const [a, b] of hit) { parts.push(value.slice(at, a), <mark key={a}>{value.slice(a, b)}</mark>); at = b; }
  parts.push(value.slice(at));
  return (
    <span className={styles.hl} data-multi={multi || undefined}>
      <span aria-hidden className={`${styles.field} ${styles.mirror}`}>{parts}</span>
      {control}
    </span>
  );
}

/** The quotes to highlight inline in the Field(s) below (a selected comment's anchored words). */
export const Quote = createContext<readonly string[]>([]);

/** String list (skills, stack, coursework…): comma-separated text, stored as string[] (kept as typed so "a, " isn't eaten). */
export function ListInput({ label, value, locked, onChange }: { label: string; value: string[]; locked: boolean; onChange: (a: string[]) => void }) {
  const [text, setText] = useState(value.join(", "));
  const parse = (t: string) => t.split(",").map((x) => x.trim()).filter(Boolean);
  // Resync only when the value prop changes (accept/undo/revert), never on every render: items with commas don't round-trip.
  const key = value.join("\n");
  const [seen, setSeen] = useState(key);
  if (key !== seen) {
    setSeen(key);
    if (parse(text).join("\n") !== key) setText(value.join(", "));
  }
  return <Field label={label} locked={locked} value={text} onChange={(t) => { setText(t); onChange(parse(t)); }} />;
}
