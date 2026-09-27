import { useId, type ReactNode } from "react";
import type { ButtonVariant } from "./Button";
import styles from "./controls.module.css";

interface UnavailableButtonProps {
  /** Plain-language reason, e.g. "Inbox sync isn't set up yet". Shown on hover and read with the button. */
  reason: string;
  variant?: ButtonVariant;
  size?: "regular" | "small";
  icon?: ReactNode;
  children: ReactNode;
}

/**
 * A control for a feature with no backend yet. It stays focusable (aria-disabled, not disabled) so keyboard and
 * screen-reader users reach it and hear why it does nothing; clicking it does nothing.
 */
export function UnavailableButton({ reason, variant = "secondary", size = "regular", icon, children }: UnavailableButtonProps) {
  const id = useId();
  return (
    <span className={styles.unavailable}>
      <button
        type="button"
        className={styles.button}
        data-variant={variant}
        data-size={size}
        aria-disabled="true"
        aria-describedby={id}
        title={reason}
        onClick={(e) => e.preventDefault()}
      >
        {icon}
        {children}
      </button>
      <span id={id} role="tooltip" className={styles.unavailableReason}>
        {reason}
      </span>
    </span>
  );
}
