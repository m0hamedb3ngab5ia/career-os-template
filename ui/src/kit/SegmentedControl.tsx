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
import styles from "./controls.module.css";

interface Ctx {
  value: string;
  select: (value: string) => void;
}
const SegmentedContext = createContext<Ctx | null>(null);

interface OptionProps {
  value: string;
  children: ReactNode;
}

function Option({ value, children }: OptionProps) {
  const ctx = use(SegmentedContext);
  if (!ctx) throw new Error("SegmentedControl.Option must be inside SegmentedControl");
  const on = ctx.value === value;
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      tabIndex={on ? 0 : -1}
      data-value={value}
      className={styles.segment}
      onClick={() => ctx.select(value)}
    >
      {children}
    </button>
  );
}

interface SegmentedControlProps {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  children: ReactNode;
}

/** A radio group drawn as a segmented control: one tab stop, arrow keys / Home / End move and select. */
function SegmentedControlRoot({ label, value, onValueChange, children }: SegmentedControlProps) {
  const ref = useRef<HTMLDivElement>(null);
  const values = Children.toArray(children)
    .filter((c): c is ReactElement<OptionProps> => isValidElement(c))
    .map((c) => c.props.value);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const i = values.indexOf(value);
    const last = values.length - 1;
    const next =
      e.key === "ArrowRight" || e.key === "ArrowDown"
        ? i >= last ? 0 : i + 1
        : e.key === "ArrowLeft" || e.key === "ArrowUp"
          ? i <= 0 ? last : i - 1
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? last
              : null;
    if (next === null) return;
    e.preventDefault();
    const v = values[next]!;
    onValueChange(v);
    ref.current?.querySelector<HTMLButtonElement>(`[data-value="${CSS.escape(v)}"]`)?.focus();
  }

  return (
    <SegmentedContext value={{ value, select: onValueChange }}>
      <div ref={ref} role="radiogroup" aria-label={label} className={styles.segmented} onKeyDown={onKeyDown}>
        {children}
      </div>
    </SegmentedContext>
  );
}

export const SegmentedControl = Object.assign(SegmentedControlRoot, { Option });
