import {
  Children,
  createContext,
  isValidElement,
  use,
  useRef,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
} from "react";
import styles from "./pills.module.css";

// Single-choice filter pills ("All", "Overdue", …). Same keyboard model as SegmentedControl: a radio group with
// one tab stop; arrow keys, Home and End move and select.

interface Ctx {
  value: string;
  select: (value: string) => void;
}
const PillContext = createContext<Ctx | null>(null);

interface PillProps {
  value: string;
  children: ReactNode;
}

function Pill({ value, children }: PillProps) {
  const ctx = use(PillContext);
  if (!ctx) throw new Error("PillGroup.Pill must be inside PillGroup");
  const on = ctx.value === value;
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      tabIndex={on ? 0 : -1}
      data-value={value}
      className={styles.pill}
      onClick={() => ctx.select(value)}
    >
      {children}
    </button>
  );
}

interface PillGroupProps {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  children: ReactNode;
}

function PillGroupRoot({ label, value, onValueChange, children }: PillGroupProps) {
  const ref = useRef<HTMLDivElement>(null);
  const values = Children.toArray(children)
    .filter((c): c is ReactElement<PillProps> => isValidElement(c))
    .map((c) => c.props.value);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const i = values.indexOf(value);
    const last = values.length - 1;
    let next: number | null = null;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = i >= last ? 0 : i + 1;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = i <= 0 ? last : i - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = last;
    if (next === null) return;
    e.preventDefault();
    const v = values[next]!;
    onValueChange(v);
    ref.current?.querySelector<HTMLButtonElement>(`[data-value="${CSS.escape(v)}"]`)?.focus();
  }

  return (
    <PillContext value={{ value, select: onValueChange }}>
      <div ref={ref} role="radiogroup" aria-label={label} className={styles.group} onKeyDown={onKeyDown}>
        {children}
      </div>
    </PillContext>
  );
}

export const PillGroup = Object.assign(PillGroupRoot, { Pill });
