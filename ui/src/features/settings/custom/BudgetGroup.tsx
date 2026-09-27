import { NumberInput } from "../../../kit/inputs";
import { FieldRow, useFieldIds } from "../FieldRow";
import { useSettingsForm } from "../form";
import { GroupCard } from "../GroupCard";
import styles from "../settings.module.css";
import type { FieldSchema, GroupSchema } from "../types";
import { isPolicy } from "../types";

const LIMITS: [string, string][] = [
  ["max_score_jobs", "Jobs scored per run"],
  ["max_prepare_jobs", "Jobs prepared per run"],
  ["max_minutes", "Time limit (min)"],
];

function Limit({ field, label, presetValue, custom }: { field: FieldSchema; label: string; presetValue: unknown; custom: boolean }) {
  const form = useSettingsForm();
  const { inputId, errId } = useFieldIds(field);
  const error = form.errors[field.id];
  const v = custom ? form.value(field.id) : presetValue;
  return (
    <div className={styles.limit} data-field={field.id}>
      <label htmlFor={inputId}>{label}</label>
      <NumberInput
        id={inputId}
        value={typeof v === "number" ? v : null}
        onValueChange={(n) => form.set(field.id, n)}
        integer
        readOnly={!custom}
        invalid={Boolean(error)}
        aria-describedby={["limits-hint", error ? errId : ""].filter(Boolean).join(" ")}
      />
      {error ? (
        <span id={errId} className={styles.error}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

/** Runs › Budget per run: preset cards, then the three limits (editable only for Custom). */
export function BudgetGroup({ group }: { group: GroupSchema }) {
  const form = useSettingsForm();
  const fields = group.items.filter((i): i is FieldSchema => !isPolicy(i));
  const preset = fields.find((f) => f.control === "preset_cards");
  const presetName = preset ? String(form.value(preset.id)) : "";
  const custom = presetName === "custom";
  const sizes = (form.value("pipeline:runs.presets") ?? {}) as Record<string, Record<string, number>>;
  const limitField = (k: string) => fields.find((f) => f.key === `runs.custom.${k}`);
  const shown = new Set([preset?.id, "pipeline:runs.presets", ...LIMITS.map(([k]) => `pipeline:runs.custom.${k}`)]);
  return (
    <GroupCard
      group={{ ...group, title: "Budget per run" }}
      note="Every run stops cleanly at the first limit it hits and records why. Any run also stops early if Claude reports your usage limit, and prepare stops once today’s apply cap is filled."
    >
      {preset ? <FieldRow field={preset} label="Preset" compact /> : null}
      <div className={styles.padded}>
        <div className={styles.limits}>
          {LIMITS.map(([k, label]) => {
            const f = limitField(k);
            return f ? <Limit key={k} field={f} label={label} presetValue={sizes[presetName]?.[k]} custom={custom} /> : null;
          })}
        </div>
        <div id="limits-hint" className={styles.hint}>
          {custom ? "Custom limits: edit any value." : "These limits come from the preset. Choose Custom to edit them."}
        </div>
      </div>
      {fields
        .filter((f) => !shown.has(f.id))
        .map((f) => (
          <FieldRow key={f.id} field={f} />
        ))}
    </GroupCard>
  );
}
