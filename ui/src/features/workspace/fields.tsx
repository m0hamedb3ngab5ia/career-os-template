import { useLayoutEffect, useRef, useState } from "react";
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
  return multi
    ? <textarea {...common} rows={1} onChange={(e) => onChange(e.target.value)} />
    : <input {...common} onChange={(e) => onChange(e.target.value)} />;
}

/** String list (skills, stack, coursework…): comma-separated text, stored as string[] (kept as typed so "a, " isn't eaten). */
export function ListInput({ label, value, locked, onChange }: { label: string; value: string[]; locked: boolean; onChange: (a: string[]) => void }) {
  const [text, setText] = useState(value.join(", "));
  const parse = (t: string) => t.split(",").map((x) => x.trim()).filter(Boolean);
  if (parse(text).join("\n") !== value.join("\n")) setText(value.join(", "));  // doc replaced (accept/undo/revert): resync
  return <Field label={label} locked={locked} value={text} onChange={(t) => { setText(t); onChange(parse(t)); }} />;
}
