import { Check, ChevronDown } from "lucide-react";
import {
  createContext,
  use,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { Button, type ButtonVariant } from "./Button";
import styles from "./overlay.module.css";

interface Ctx {
  open: boolean;
  setOpen: (open: boolean, focusTrigger?: boolean) => void;
  label: string;
  menuId: string;
  triggerRef: RefObject<HTMLButtonElement | null>;
  menuRef: RefObject<HTMLDivElement | null>;
}
const MenuContext = createContext<Ctx | null>(null);

function useMenu(part: string): Ctx {
  const ctx = use(MenuContext);
  if (!ctx) throw new Error(`Menu.${part} must be inside Menu`);
  return ctx;
}

const ITEM = '[role="menuitem"]:not([aria-disabled="true"]), [role="menuitemcheckbox"], [role="menuitemradio"]';

function items(menu: HTMLElement | null): HTMLElement[] {
  return menu ? Array.from(menu.querySelectorAll<HTMLElement>(ITEM)) : [];
}

export interface MenuItem {
  key: string;
  label: string;
  /** Shown instead of acting (e.g. the card's current column). */
  disabled?: boolean;
  onSelect: () => void;
}

interface MenuRootProps {
  /** Accessible name of the menu itself ("Move Acme to"). */
  label: string;
  /** Compound parts (Menu.Trigger + Menu.Content), or, with `items`, the trigger's text ("Move to…"). */
  children: ReactNode;
  /** Shorthand for a plain action menu: renders the trigger and one Menu.Item per entry. */
  items?: MenuItem[];
  size?: "regular" | "small";
}

/**
 * Menu button (WAI-ARIA APG): the trigger opens a `role="menu"`; arrows, Home and End move (skipping disabled
 * items), Enter picks, Escape closes and returns focus to the trigger, Tab closes.
 */
function MenuRoot({ label, children, items: list, size }: MenuRootProps) {
  const [open, setOpenState] = useState(false);
  const menuId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const setOpen = (next: boolean, focusTrigger = false) => {
    setOpenState(next);
    if (!next && focusTrigger) triggerRef.current?.focus();
  };
  return (
    <MenuContext value={{ open, setOpen, label, menuId, triggerRef, menuRef }}>
      <div className={styles.menuRoot}>
        {list ? (
          <>
            <Trigger size={size}>
              {children}
              <ChevronDown size={12} strokeWidth={1.7} aria-hidden="true" />
            </Trigger>
            <Content align="end">
              {list.map((it) => (
                <Item key={it.key} disabled={it.disabled} onSelect={it.onSelect}>
                  {it.label}
                </Item>
              ))}
            </Content>
          </>
        ) : (
          children
        )}
      </div>
    </MenuContext>
  );
}

interface TriggerProps {
  children: ReactNode;
  icon?: ReactNode;
  variant?: ButtonVariant;
  size?: "regular" | "small";
  pending?: boolean;
  pendingLabel?: string;
  disabled?: boolean;
}

function Trigger({ children, ...rest }: TriggerProps) {
  const ctx = useMenu("Trigger");
  return (
    <Button
      {...rest}
      ref={ctx.triggerRef}
      aria-haspopup="menu"
      aria-expanded={ctx.open}
      aria-controls={ctx.open ? ctx.menuId : undefined}
      onClick={() => ctx.setOpen(!ctx.open)}
      onKeyDown={(e) => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          ctx.setOpen(true);
        }
      }}
    >
      {children}
    </Button>
  );
}

function Content({ children, align = "start" }: { children: ReactNode; align?: "start" | "end" }) {
  const ctx = useMenu("Content");
  const { open, setOpen, menuRef, triggerRef } = ctx;

  useEffect(() => {
    if (!open) return;
    const list = items(menuRef.current);
    const checked = list.find((el) => el.getAttribute("aria-checked") === "true");
    (checked ?? list[0])?.focus();
    function onPointer(e: PointerEvent) {
      const t = e.target as Node;
      if (menuRef.current?.contains(t) || triggerRef.current?.contains(t)) return;
      setOpen(false);
    }
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  if (!open) return null;

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const list = items(menuRef.current);
    const i = list.indexOf(document.activeElement as HTMLElement);
    const last = list.length - 1;
    let next: number | null = null;
    if (e.key === "ArrowDown") next = i >= last ? 0 : i + 1;
    else if (e.key === "ArrowUp") next = i <= 0 ? last : i - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = last;
    else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false, true);
      return;
    } else if (e.key === "Tab") {
      setOpen(false);
      return;
    }
    if (next === null) return;
    e.preventDefault();
    list[next]?.focus();
  }

  return (
    <div
      ref={menuRef}
      id={ctx.menuId}
      role="menu"
      aria-label={ctx.label}
      className={styles.menu}
      data-align={align}
      onKeyDown={onKeyDown}
    >
      {children}
    </div>
  );
}

interface ItemBase {
  children: ReactNode;
  disabled?: boolean;
}

function ItemButton({
  role,
  checked,
  onActivate,
  closeOnSelect,
  disabled,
  children,
}: ItemBase & {
  role: "menuitem" | "menuitemcheckbox" | "menuitemradio";
  checked?: boolean;
  onActivate: () => void;
  closeOnSelect: boolean;
}) {
  const ctx = useMenu("Item");
  return (
    <button
      type="button"
      role={role}
      aria-checked={checked}
      aria-disabled={disabled || undefined}
      tabIndex={-1}
      className={styles.menuItem}
      onClick={() => {
        if (disabled) return;
        if (closeOnSelect) ctx.setOpen(false, true);
        onActivate();
      }}
    >
      <span className={styles.menuCheck} aria-hidden="true">
        {checked ? <Check size={14} strokeWidth={2} /> : null}
      </span>
      {children}
    </button>
  );
}

function Item({ onSelect, ...rest }: ItemBase & { onSelect: () => void }) {
  return <ItemButton role="menuitem" onActivate={onSelect} closeOnSelect {...rest} />;
}

function RadioItem({ checked, onSelect, ...rest }: ItemBase & { checked: boolean; onSelect: () => void }) {
  return <ItemButton role="menuitemradio" checked={checked} onActivate={onSelect} closeOnSelect {...rest} />;
}

/** Toggles without closing, so several columns can be switched in one visit. */
function CheckboxItem({
  checked,
  onCheckedChange,
  ...rest
}: ItemBase & { checked: boolean; onCheckedChange: (checked: boolean) => void }) {
  return (
    <ItemButton
      role="menuitemcheckbox"
      checked={checked}
      onActivate={() => onCheckedChange(!checked)}
      closeOnSelect={false}
      {...rest}
    />
  );
}

export const Menu = Object.assign(MenuRoot, { Trigger, Content, Item, RadioItem, CheckboxItem });
