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

/** One toast at a time in a polite live region that is always mounted, so screen readers hear each one. */
export function ToastProvider({ defaultSeconds = 8, children }: { defaultSeconds?: number; children: ReactNode }) {
  const [current, setCurrent] = useState<Current | null>(null);
  const seq = useRef(0);

  const dismiss = useCallback(() => setCurrent(null), []);
  const show = useCallback((t: ToastOptions) => {
    seq.current += 1;
    setCurrent({ ...t, key: seq.current });
  }, []);

  const key = current?.key;
  const seconds = current?.seconds ?? defaultSeconds;
  useEffect(() => {
    if (key === undefined) return;
    const timer = setTimeout(() => setCurrent((c) => (c?.key === key ? null : c)), seconds * 1000);
    return () => clearTimeout(timer);
  }, [key, seconds]);

  const api = useMemo(() => ({ show, dismiss }), [show, dismiss]);

  return (
    <ToastContext value={api}>
      {children}
      <div role="status" aria-live="polite" className={styles.toastRegion}>
        {current ? (
          <div key={current.key} className={styles.toast}>
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
