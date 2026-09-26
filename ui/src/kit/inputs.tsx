import { X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ComponentProps, type KeyboardEvent, type ReactNode } from "react";
import styles from "./inputs.module.css";

// Compact form inputs for grouped Settings rows. Every input is controlled and takes an accessible name from a
// <label htmlFor> in the row (or aria-label). `invalid` sets aria-invalid; the row renders the message.

type Base = { invalid?: boolean; className?: string };

function cls(...c: (string | false | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function TextInput({
  value,
  onValueChange,
  invalid,
  className,
  ...rest
}: Base & Omit<ComponentProps<"input">, "value" | "onChange"> & { value: string; onValueChange: (v: string) => void }) {
  return (
    <input
      type="text"
      autoComplete="off"
      spellCheck={false}
      {...rest}
      className={cls(styles.input, styles.text, className)}
      aria-invalid={invalid || undefined}
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
    />
  );
}

function toText(v: number | null) {
  return v === null || Number.isNaN(v) ? "" : String(v);
}

/**
 * A number field that lets you type freely ("", "1.") and reports a number (or null when empty) on every change.
 * Invalid text is reported as NaN so the form can show "Enter a number."
 */
export function NumberInput({
  value,
  onValueChange,
  invalid,
  className,
  integer,
  ...rest
}: Base &
  Omit<ComponentProps<"input">, "value" | "onChange" | "type"> & {
    value: number | null;
    onValueChange: (v: number | null) => void;
    integer?: boolean;
  }) {
  const [text, setText] = useState(() => toText(value));
  const last = useRef(value);
  useEffect(() => {
    if (!Object.is(value, last.current)) {
      last.current = value;
      setText(toText(value));
    }
  }, [value]);
  return (
    <input
      type="text"
      inputMode={integer ? "numeric" : "decimal"}
      autoComplete="off"
      {...rest}
      className={cls(styles.input, styles.number, className)}
      aria-invalid={invalid || undefined}
      value={text}
      onChange={(e) => {
        const t = e.target.value;
        setText(t);
        const trimmed = t.trim().replace(",", ".");
        const n = trimmed === "" ? null : Number(trimmed);
        last.current = n;
        onValueChange(n);
      }}
    />
  );
}

export interface SelectOption {
  value: string;
  label: string;
}

export function SelectInput({
  value,
  onValueChange,
  options,
  invalid,
  className,
  ...rest
}: Base &
  Omit<ComponentProps<"select">, "value" | "onChange"> & {
    value: string;
    onValueChange: (v: string) => void;
    options: SelectOption[];
  }) {
  return (
    <select
      {...rest}
      className={cls(styles.input, styles.select, className)}
      aria-invalid={invalid || undefined}
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function TimeInput({
  value,
  onValueChange,
  invalid,
  className,
  ...rest
}: Base & Omit<ComponentProps<"input">, "value" | "onChange" | "type"> & { value: string; onValueChange: (v: string) => void }) {
  return (
    <input
      type="time"
      {...rest}
      className={cls(styles.input, styles.time, className)}
      aria-invalid={invalid || undefined}
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
    />
  );
}

export function RangeInput({
  value,
  onValueChange,
  className,
  ...rest
}: Omit<ComponentProps<"input">, "value" | "onChange" | "type"> & {
  value: number;
  onValueChange: (v: number) => void;
  className?: string;
}) {
  return (
    <input
      type="range"
      {...rest}
      className={cls(styles.range, className)}
      value={value}
      onChange={(e) => onValueChange(Number(e.target.value))}
    />
  );
}

/** An input with its unit beside it ("30 days"). */
export function WithUnit({ unit, id, children }: { unit?: string; id?: string; children: ReactNode }) {
  return (
    <span className={styles.withUnit}>
      {children}
      {unit ? <span id={id}>{unit}</span> : null}
    </span>
  );
}

interface TagEditorProps {
  /** Names the list: "Allowed ATS". */
  label: string;
  values: string[];
  onValuesChange: (v: string[]) => void;
  /** Choices: with `strict` only these can be added (a select), otherwise they are suggestions. */
  options?: string[];
  strict?: boolean;
  format?: (v: string) => string;
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
  tone?: "blue" | "gray";
  /** Id for the add field, so a row label can point at it. */
  inputId?: string;
}

/** Removable chips plus an add field (Enter or comma adds). Backspace in an empty field removes the last chip. */
export function TagEditor({
  label,
  values,
  onValuesChange,
  options = [],
  strict = false,
  format = (v) => v,
  disabled,
  invalid,
  describedBy,
  tone = "blue",
  inputId,
}: TagEditorProps) {
  const listId = useId();
  const [draft, setDraft] = useState("");
  const remaining = options.filter((o) => !values.includes(o));

  function add(raw: string) {
    const v = raw.trim();
    if (!v || values.includes(v)) return setDraft("");
    onValuesChange([...values, v]);
    setDraft("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(draft);
    } else if (e.key === "Backspace" && draft === "" && values.length) {
      onValuesChange(values.slice(0, -1));
    }
  }

  return (
    <div className={styles.tags}>
      <ul className={styles.tags} aria-label={label}>
        {values.length === 0 ? <li className={styles.tagEmpty}>None</li> : null}
        {values.map((v) => (
          <li key={v}>
            <span className={styles.tag} data-tone={tone}>
              <span translate="no">{format(v)}</span>
              {disabled ? null : (
                <button
                  type="button"
                  className={styles.tagRemove}
                  aria-label={`Remove ${format(v)}`}
                  onClick={() => onValuesChange(values.filter((x) => x !== v))}
                >
                  <X size={12} strokeWidth={2} aria-hidden="true" />
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>
      {disabled ? null : strict ? (
        remaining.length ? (
          <select
            id={inputId}
            className={cls(styles.input, styles.select)}
            aria-label={`Add to ${label}`}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            value=""
            onChange={(e) => e.target.value && onValuesChange([...values, e.target.value])}
          >
            <option value="">Add…</option>
            {remaining.map((o) => (
              <option key={o} value={o}>
                {format(o)}
              </option>
            ))}
          </select>
        ) : null
      ) : (
        <>
          <input
            id={inputId}
            type="text"
            autoComplete="off"
            spellCheck={false}
            className={cls(styles.input, styles.tagAdd)}
            placeholder="Add…"
            aria-label={`Add to ${label}`}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            list={remaining.length ? listId : undefined}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            onBlur={() => draft.trim() && add(draft)}
          />
          {remaining.length ? (
            <datalist id={listId}>
              {remaining.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
          ) : null}
        </>
      )}
    </div>
  );
}
