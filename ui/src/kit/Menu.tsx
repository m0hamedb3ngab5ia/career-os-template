import { ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import styles from "./menus.module.css";

export interface MenuItem {
  key: string;
  label: string;
  /** Shown instead of acting (e.g. the card's current column). */
  disabled?: boolean;
  onSelect: () => void;
}

interface MenuProps {
  /** Button text ("Move to…"). */
  children: ReactNode;
  /** Accessible name of the menu itself ("Move Acme to"). */
  label: string;
  items: MenuItem[];
  size?: "regular" | "small";
}

/**
 * Menu button: Enter / Space / ArrowDown open it with focus on the first enabled item; arrows, Home and End move
 * (roving focus); Enter picks; Escape closes and returns focus to the button; Tab closes.
 */
export function Menu({ children, label, items, size = "regular" }: MenuProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const enabled = items.map((it, i) => (it.disabled ? -1 : i)).filter((i) => i >= 0);
  const [active, setActive] = useState(enabled[0] ?? 0);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.focus();
  }, [open, active]);

  useEffect(() => {
    if (!open) return;
    function onPointer(e: PointerEvent) {
      const t = e.target as Node;
      if (menuRef.current?.contains(t) || buttonRef.current?.contains(t)) return;
      setOpen(false);
    }
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  function show(at: "first" | "last") {
    setActive((at === "first" ? enabled[0] : enabled.at(-1)) ?? 0);
    setOpen(true);
  }

  function close(focusButton = true) {
    setOpen(false);
    if (focusButton) buttonRef.current?.focus();
  }

  function onMenuKey(e: KeyboardEvent<HTMLDivElement>) {
    const pos = enabled.indexOf(active);
    if (e.key === "ArrowDown") setActive(enabled[(pos + 1) % enabled.length] ?? active);
    else if (e.key === "ArrowUp") setActive(enabled[(pos - 1 + enabled.length) % enabled.length] ?? active);
    else if (e.key === "Home") setActive(enabled[0] ?? active);
    else if (e.key === "End") setActive(enabled.at(-1) ?? active);
    else if (e.key === "Escape") {
      e.stopPropagation();
      close();
    } else if (e.key === "Tab") {
      close(false);
      return;
    } else return;
    e.preventDefault();
  }

  return (
    <span className={styles.anchor}>
      <button
        ref={buttonRef}
        type="button"
        className={styles.trigger}
        data-size={size}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? `${id}-menu` : undefined}
        onClick={() => (open ? close() : show("first"))}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            show(e.key === "ArrowDown" ? "first" : "last");
          }
        }}
      >
        {children}
        <ChevronDown size={12} strokeWidth={1.7} aria-hidden="true" />
      </button>
      {open ? (
        <div ref={menuRef} id={`${id}-menu`} role="menu" aria-label={label} className={styles.popup} data-align="end"
          onKeyDown={onMenuKey}>
          {items.map((it, i) => (
            <button
              key={it.key}
              type="button"
              role="menuitem"
              data-index={i}
              tabIndex={i === active ? 0 : -1}
              aria-disabled={it.disabled || undefined}
              className={styles.option}
              onClick={() => {
                if (it.disabled) return;
                close();
                it.onSelect();
              }}
            >
              {it.label}
            </button>
          ))}
        </div>
      ) : null}
    </span>
  );
}
