import { useRef, type KeyboardEvent } from "react";
import { useSettingsForm } from "../form";
import { equal, formatDuration, optionLabel } from "../format";
import styles from "../settings.module.css";
import type { ControlProps } from "./types";

type Sizes = { max_score_jobs?: number; max_prepare_jobs?: number; max_minutes?: number };

export function presetDetail(name: string, sizes: Sizes | undefined): string {
  if (!sizes) return name === "custom" ? "your own limits" : "";
  const parts = [];
  if (sizes.max_score_jobs !== undefined) parts.push(`score ${sizes.max_score_jobs}`);
  if (sizes.max_prepare_jobs !== undefined) parts.push(`prepare ${sizes.max_prepare_jobs}`);
  if (sizes.max_minutes !== undefined) parts.push(formatDuration(sizes.max_minutes * 60));
  return parts.join(" · ");
}

/** A radio group of cards (runs.preset). Sizes come from runs.presets; Custom shows your own limits.
 * One tab stop; arrow keys, Home and End move and select. */
export function PresetCardsControl({ field, value, onChange, inputId, describedBy, disabled }: ControlProps) {
  const form = useSettingsForm();
  const ref = useRef<HTMLDivElement>(null);
  const sizes = (form.value("pipeline:runs.presets") ?? {}) as Record<string, Sizes>;
  const names = field.options.map(String);
  const custom: Sizes = {
    max_score_jobs: form.value("pipeline:runs.custom.max_score_jobs") as number,
    max_prepare_jobs: form.value("pipeline:runs.custom.max_prepare_jobs") as number,
    max_minutes: form.value("pipeline:runs.custom.max_minutes") as number,
  };

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const i = names.indexOf(String(value));
    const last = names.length - 1;
    const next =
      e.key === "ArrowRight" || e.key === "ArrowDown"
        ? i >= last ? 0 : i + 1
        : e.key === "ArrowLeft" || e.key === "ArrowUp"
          ? i <= 0 ? last : i - 1
          : e.key === "Home" ? 0 : e.key === "End" ? last : null;
    if (next === null || disabled) return;
    e.preventDefault();
    onChange(names[next]);
    ref.current?.querySelectorAll<HTMLButtonElement>("[role=radio]")[next]?.focus();
  }

  return (
    <div ref={ref} role="radiogroup" aria-label={field.label} aria-describedby={describedBy} className={styles.presetGrid}
      onKeyDown={onKeyDown}>
      {names.map((n, i) => {
        const on = n === value;
        const rec = field.recommended && equal(n, field.default);
        return (
          <button
            key={n}
            id={on || (i === 0 && !names.includes(String(value))) ? inputId : undefined}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on || (i === 0 && !names.includes(String(value))) ? 0 : -1}
            className={styles.presetCard}
            onClick={() => onChange(n)}
            disabled={disabled}
          >
            <span className={styles.presetName}>{optionLabel(n)}</span>
            <span className={styles.presetDetail}>{n === "custom" ? presetDetail(n, custom) || "your own limits" : presetDetail(n, sizes[n])}</span>
            {rec ? <span className={styles.presetRec}>Recommended</span> : null}
          </button>
        );
      })}
    </div>
  );
}
