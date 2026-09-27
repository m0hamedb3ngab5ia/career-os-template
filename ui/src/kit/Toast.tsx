import { createContext, use, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import styles from "./controls.module.css";

export interface ToastOptions {
  message: string;
  /** Reversible actions act now and offer Undo (docs: "act now, show Undo for 8 s"). */
  onUndo?: () => void;
  undoLabel?: string;
  /** How long it stays; defaults to the provider's `defaultSeconds`. */
  seconds?: number;
}

interface ToastApi {
  show: (t: ToastOptions) => void;
  dismiss: () => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = use(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}

interface Current extends ToastOptions {
  key: number;
}

/**
 * One toast at a time in a polite live region that is always mounted, so screen readers hear each one.
 * The countdown pauses while the toast is hovered or has focus, and a toast that closes while focused hands
 * focus back to whatever had it before the toast appeared.
 */
export function ToastProvider({ defaultSeconds = 8, children }: { defaultSeconds?: number; children: ReactNode }) {
  const [current, setCurrent] = useState<Current | null>(null);
  const seq = useRef(0);
  const el = useRef<HTMLDivElement>(null);
  const prevFocus = useRef<HTMLElement | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const remaining = useRef(0);
  const startedAt = useRef(0);
  const hovered = useRef(false);
  const focused = useRef(false);

  const dismiss = useCallback(() => {
    clearTimeout(timer.current);
    timer.current = undefined;
    if (el.current?.contains(document.activeElement)) prevFocus.current?.focus();
    hovered.current = focused.current = false;
    setCurrent(null);
  }, []);

  const run = useCallback(() => {
    clearTimeout(timer.current);
    if (hovered.current || focused.current) return;
    startedAt.current = Date.now();
    timer.current = setTimeout(dismiss, remaining.current);
  }, [dismiss]);

  const pause = useCallback(() => {
    if (timer.current === undefined) return;
    clearTimeout(timer.current);
    timer.current = undefined;
    remaining.current = Math.max(0, remaining.current - (Date.now() - startedAt.current));
  }, []);

  const show = useCallback(
    (t: ToastOptions) => {
      seq.current += 1;
      const active = document.activeElement;
      prevFocus.current = active instanceof HTMLElement && !el.current?.contains(active) ? active : prevFocus.current;
      remaining.current = (t.seconds ?? defaultSeconds) * 1000;
      hovered.current = focused.current = false;
      setCurrent({ ...t, key: seq.current });
    },
    [defaultSeconds],
  );

  const key = current?.key;
  useEffect(() => {
    if (key === undefined) return;
    run();
    return () => clearTimeout(timer.current);
  }, [key, run]);

  const api = useMemo(() => ({ show, dismiss }), [show, dismiss]);

  const hold = (which: typeof hovered) => () => {
    which.current = true;
    pause();
  };
  const release = (which: typeof hovered) => () => {
    which.current = false;
    run();
  };

  return (
    <ToastContext value={api}>
      {children}
      <div role="status" aria-live="polite" className={styles.toastRegion}>
        {current ? (
          <div
            key={current.key}
            ref={el}
            className={styles.toast}
            onMouseEnter={hold(hovered)}
            onMouseLeave={release(hovered)}
            onFocus={hold(focused)}
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node | null)) release(focused)();
            }}
          >
            <span className={styles.toastMessage}>{current.message}</span>
            {current.onUndo ? (
              <button
                type="button"
                className={styles.toastAction}
                onClick={() => {
                  current.onUndo?.();
                  dismiss();
                }}
              >
                {current.undoLabel ?? "Undo"}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </ToastContext>
  );
}
