import styles from "./controls.module.css";

interface MeterProps {
  /** What is measured ("Time budget"); also the progress bar's accessible name. */
  label: string;
  value: number;
  max: number;
  /** Visible value text ("21 of 90 min"); also read out as aria-valuetext. */
  valueText: string;
  /** Extra words after the value text, shown only ("prepare stops at the cap"). */
  note?: string;
}

/** A labelled budget meter: label and value on one line, a thin bar under them. */
export function Meter({ label, value, max, valueText, note }: MeterProps) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div className={styles.meter}>
      <div className={styles.meterHead}>
        <span>{label}</span>
        <span className={styles.meterValue}>
          {valueText}
          {note ? ` · ${note}` : null}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={Math.min(value, max)}
        aria-valuetext={valueText}
        className={styles.meterTrack}
      >
        <div className={styles.meterFill} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
