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
import { formatCount } from "../lib/format";
import styles from "./overlay.module.css";

interface Ctx {
  value: string;
  select: (value: string) => void;
  controls?: string;
}
const TabsContext = createContext<Ctx | null>(null);

interface TabProps {
  value: string;
  /** Shown after the label as "(59)". */
  count?: number | null;
  children: ReactNode;
}

function Tab({ value, count, children }: TabProps) {
  const ctx = use(TabsContext);
  if (!ctx) throw new Error("Tabs.Tab must be inside Tabs");
  const on = ctx.value === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={on}
      aria-controls={ctx.controls}
      tabIndex={on ? 0 : -1}
      data-value={value}
      className={styles.tab}
      onClick={() => ctx.select(value)}
    >
      {children}
      {count !== undefined && count !== null ? (
        <>
          {" "}
          <span className="tabular">({formatCount(count)})</span>
        </>
      ) : null}
    </button>
  );
}

interface TabsProps {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  /** Id of the panel the tabs filter. */
  controls?: string;
  children: ReactNode;
}

/** Filter tabs: one tab stop, arrow keys / Home / End move and select (automatic activation). */
function TabsRoot({ label, value, onValueChange, controls, children }: TabsProps) {
  const ref = useRef<HTMLDivElement>(null);
  const values = Children.toArray(children)
    .filter((c): c is ReactElement<TabProps> => isValidElement(c))
    .map((c) => c.props.value);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const i = values.indexOf(value);
    const last = values.length - 1;
    const next =
      e.key === "ArrowRight"
        ? i >= last ? 0 : i + 1
        : e.key === "ArrowLeft"
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
    <TabsContext value={{ value, select: onValueChange, controls }}>
      <div ref={ref} role="tablist" aria-label={label} className={styles.tabs} onKeyDown={onKeyDown}>
        {children}
      </div>
    </TabsContext>
  );
}

export const Tabs = Object.assign(TabsRoot, { Tab });
