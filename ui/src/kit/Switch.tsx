import { useId } from "react";
import styles from "./controls.module.css";

interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  /** Name the setting, not the state ("Scout schedule", not "On"). */
  label: string;
  /** Hide the visible label when the row already shows it; it stays the accessible name. */
  labelHidden?: boolean;
  disabled?: boolean;
}

export function Switch({ checked, onCheckedChange, label, labelHidden = false, disabled }: SwitchProps) {
  const id = useId();
  return (
    <label className={styles.switchRow}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={id}
        className={styles.switch}
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
      >
        <span className={styles.knob} aria-hidden="true" />
      </button>
      <span id={id} className={labelHidden ? "sr-only" : undefined}>
        {label}
      </span>
    </label>
  );
}
