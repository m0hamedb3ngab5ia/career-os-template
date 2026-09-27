import { Lock } from "lucide-react";
import { useState, type ComponentType } from "react";
import { Button } from "../../kit/Button";
import { NumberControl, SelectControl, SliderControl, SwitchControl, TagsControl, TextControl, TimeControl } from "./controls/basic";
import {
  KeyValueControl,
  RecordsControl,
  ReasonLevelsControl,
  RuleListControl,
  TimeRangeControl,
} from "./controls/editors";
import { PresetCardsControl } from "./controls/PresetCards";
import { ScheduleControl } from "./controls/ScheduleControl";
import type { ControlProps } from "./controls/types";
import { useSettingsForm } from "./form";
import { domId, equal, formatValue } from "./format";
import { RichText } from "./RichText";
import styles from "./settings.module.css";
import type { FieldSchema, PolicyItem } from "./types";

function Unsupported({ field }: ControlProps) {
  return <span className={styles.hint}>This setting ({field.control}) can't be edited here yet; edit the YAML file.</span>;
}

export const CONTROLS: Record<string, ComponentType<ControlProps>> = {
  switch: SwitchControl,
  number: NumberControl,
  slider: SliderControl,
  select: SelectControl,
  preset_cards: PresetCardsControl,
  text: TextControl,
  time: TimeControl,
  time_range: TimeRangeControl,
  tags: TagsControl,
  rule_list: RuleListControl,
  reason_levels: ReasonLevelsControl,
  schedule: ScheduleControl,
  key_value: KeyValueControl,
  records: RecordsControl,
};

// Controls whose own element carries the label (a <label htmlFor> can point at them).
const LABELLABLE = new Set(["number", "slider", "select", "text", "time"]);
// Wide controls sit under the label instead of beside it.
const STACKED = new Set(["tags", "rule_list", "reason_levels", "key_value", "records", "preset_cards"]);

/** Turning these on needs a confirm: they let career-os submit without a final review. */
export function confirmFor(field: FieldSchema): { title: string; body: string } | null {
  const tier = /^tiers\.([A-Z])\.auto_submit$/.exec(field.key);
  if (tier) {
    return {
      title: `Turn on auto-submit for Tier ${tier[1]}?`,
      body: `When you run Apply, matching Tier ${tier[1]} jobs submit without a final review from you.`,
    };
  }
  if (field.key === "runs.auto_submit.enabled") {
    return {
      title: "Let scheduled runs submit?",
      body: "Jobs matching the allowed rules will submit overnight without you.",
    };
  }
  return null;
}

/** "Recommended" when the value is the default, "Recommended: 30 days" when it differs. */
export function RecommendedNote({ field, value }: { field: FieldSchema; value: unknown }) {
  if (!field.recommended || field.personal || field.locked || field.readonly) return null;
  if (field.default === null && !field.nullable) return null;
  if (equal(value, field.default)) return <span className={styles.recommended}>Recommended</span>;
  const d = formatValue(field, field.default);
  return d ? <span className={styles.recommended}>Recommended: {d}</span> : null;
}

export function useFieldIds(field: FieldSchema) {
  return { inputId: domId("f", field.id), hintId: domId("hint", field.id), errId: domId("err", field.id) };
}

interface FieldRowProps {
  field: FieldSchema;
  /** Override the label shown in the row (tier cards use short labels). */
  label?: string;
  /** Hide the "Recommended" note and help text (tight layouts). */
  compact?: boolean;
  /** Screen-reader-only prefix that makes repeated labels unique ("Tier A: "). */
  namePrefix?: string;
}

export function FieldRow({ field, label, compact = false, namePrefix = "" }: FieldRowProps) {
  const form = useSettingsForm();
  const value = form.value(field.id);
  const error = form.errors[field.id];
  const [asking, setAsking] = useState(false);
  const { inputId, hintId, errId } = useFieldIds(field);
  const editable = !field.locked && !field.readonly;
  const Control = CONTROLS[field.control] ?? Unsupported;
  const confirm = confirmFor(field);
  const hint = [compact ? "" : field.help, !editable ? field.note : ""].filter(Boolean).join(" ");
  const describedBy = [hint ? hintId : "", error ? errId : ""].filter(Boolean).join(" ") || undefined;
  const text = label ?? field.label;

  function onChange(v: unknown) {
    if (confirm && v === true && field.control === "switch") return setAsking(true);
    setAsking(false);
    form.set(field.id, v);
  }

  return (
    <div className={styles.row} data-field={field.id} data-layout={STACKED.has(field.control) ? "stack" : "inline"}>
      <div className={styles.rowMain}>
        <div className={styles.rowText}>
          {LABELLABLE.has(field.control) ? (
            <label htmlFor={inputId} className={styles.rowLabel}>
              {namePrefix ? <span className="sr-only">{namePrefix.trimEnd()} </span> : null}
              <RichText text={text} />
            </label>
          ) : (
            <div className={styles.rowLabel}>
              <RichText text={text} />
            </div>
          )}
          {hint ? (
            <div id={hintId} className={styles.hint}>
              <RichText text={hint} />
            </div>
          ) : null}
        </div>
        <div className={styles.rowControl}>
          {field.locked ? (
            <span className={styles.locked}>
              <Lock size={13} strokeWidth={1.7} aria-hidden="true" />
              Locked
            </span>
          ) : null}
          <Control
            field={{ ...field, label: namePrefix + text.replace(/`/g, "") }}
            value={value}
            onChange={onChange}
            inputId={inputId}
            describedBy={describedBy}
            invalid={Boolean(error)}
            disabled={!editable}
          />
          {compact ? null : <RecommendedNote field={field} value={value} />}
        </div>
      </div>
      {asking && confirm ? (
        <div className={styles.confirmTurnOn} role="alertdialog" aria-labelledby={`${inputId}-q`}
          onKeyDown={(e) => e.key === "Escape" && setAsking(false)}>
          <div id={`${inputId}-q`} className={styles.confirmTitle}>
            {confirm.title}
          </div>
          <div>{confirm.body}</div>
          <div className={styles.confirmActions}>
            <Button size="small" onClick={() => setAsking(false)} autoFocus>
              Cancel
            </Button>
            <Button
              size="small"
              variant="primary"
              onClick={() => {
                setAsking(false);
                form.set(field.id, true);
              }}
            >
              Turn on
            </Button>
          </div>
        </div>
      ) : null}
      {error ? (
        <div id={errId} className={styles.error}>
          {error}
        </div>
      ) : null}
    </div>
  );
}

export function PolicyRow({ item }: { item: PolicyItem }) {
  return (
    <div className={styles.row}>
      <div className={styles.rowMain}>
        <div className={styles.rowText}>
          <div className={styles.rowLabel}>{item.label}</div>
          {item.why ? (
            <div className={styles.hint}>
              <RichText text={item.why} />
            </div>
          ) : null}
        </div>
        <span className={styles.locked}>
          <Lock size={13} strokeWidth={1.7} aria-hidden="true" />
          {item.value}
        </span>
      </div>
    </div>
  );
}
