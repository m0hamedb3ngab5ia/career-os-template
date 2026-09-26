import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import styles from "./menus.module.css";

export interface ListboxOption {
  value: string;
  label: string;
}

interface ListboxProps {
  /** Visible text before the value ("Group by", "Tier"). Also the accessible name. */
  label: string;
  /** "inline" draws "Tier: All" inside the button; "outside" draws the label as a caption before it. */
  labelPlacement?: "inline" | "outside";
  value: string;
  options: ListboxOption[];
  onValueChange: (value: string) => void;
}

/**
 * A select drawn as the mockup's small button + popup list. One tab stop; the popup opens with Enter, Space or
 * ArrowDown, arrows / Home / End move, Enter or click picks, Escape and Tab close and return focus to the button.
 */
export function Listbox({ label, labelPlacement = "outside", value, options, onValueChange }: ListboxProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const current = options.find((o) => o.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    listRef.current?.focus();
    function onPointer(e: PointerEvent) {
      const t = e.target as Node;
      if (listRef.current?.contains(t) || buttonRef.current?.contains(t)) return;
      setOpen(false);
    }
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  function openAt(i: number) {
    setActive(Math.max(0, i));
    setOpen(true);
  }

  function close(focusButton = true) {
    setOpen(false);
    if (focusButton) buttonRef.current?.focus();
  }

  function pick(i: number) {
    const o = options[i];
    if (o) onValueChange(o.value);
    close();
  }

  function onButtonKey(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      openAt(options.findIndex((o) => o.value === value));
    }
  }

  function onListKey(e: KeyboardEvent<HTMLUListElement>) {
    const last = options.length - 1;
    if (e.key === "ArrowDown") setActive((a) => (a >= last ? last : a + 1));
    else if (e.key === "ArrowUp") setActive((a) => (a <= 0 ? 0 : a - 1));
    else if (e.key === "Home") setActive(0);
    else if (e.key === "End") setActive(last);
    else if (e.key === "Enter" || e.key === " ") pick(active);
    else if (e.key === "Escape") {
      e.stopPropagation();
      close();
    } else if (e.key === "Tab") {
      close(false);
      return;
    } else return;
    e.preventDefault();
  }

  const labelId = `${id}-label`;
  return (
    <span className={styles.anchor}>
      {labelPlacement === "outside" ? (
        <span id={labelId} className={styles.caption}>
          {label}
        </span>
      ) : null}
      <button
        ref={buttonRef}
        type="button"
        id={`${id}-button`}
        className={styles.trigger}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? `${id}-list` : undefined}
        aria-labelledby={labelPlacement === "outside" ? `${labelId} ${id}-button` : undefined}
        onClick={() => (open ? close() : openAt(options.findIndex((o) => o.value === value)))}
        onKeyDown={onButtonKey}
      >
        {labelPlacement === "inline" ? `${label}: ` : null}
        {current?.label}
        <ChevronDown size={12} strokeWidth={1.7} aria-hidden="true" />
      </button>
      {open ? (
        <ul
          ref={listRef}
          id={`${id}-list`}
          role="listbox"
          tabIndex={-1}
          aria-label={label}
          aria-activedescendant={`${id}-opt-${active}`}
          className={styles.popup}
          onKeyDown={onListKey}
        >
          {options.map((o, i) => (
            <li
              key={o.value}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={o.value === value}
              data-active={i === active || undefined}
              className={styles.option}
              onPointerMove={() => setActive(i)}
              onClick={() => pick(i)}
            >
              <span className={styles.check} aria-hidden="true">
                {o.value === value ? <Check size={13} strokeWidth={2} /> : null}
              </span>
              {o.label}
            </li>
          ))}
        </ul>
      ) : null}
    </span>
  );
}
