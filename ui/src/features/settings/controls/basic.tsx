import { NumberInput, RangeInput, SelectInput, TagEditor, TextInput, TimeInput, WithUnit } from "../../../kit/inputs";
import { Switch } from "../../../kit/Switch";
import { equal, formatNumber, optionLabel } from "../format";
import styles from "../settings.module.css";
import type { ControlProps } from "./types";

export function SwitchControl({ field, value, onChange, describedBy, disabled }: ControlProps) {
  return (
    <Switch
      checked={Boolean(value)}
      onCheckedChange={onChange}
      label={field.label}
      labelHidden
      describedBy={describedBy}
      disabled={disabled}
    />
  );
}

export function NumberControl({ field, value, onChange, inputId, describedBy, invalid, disabled }: ControlProps) {
  const unitId = `${inputId}-unit`;
  return (
    <WithUnit unit={field.unit} id={unitId}>
      <NumberInput
        id={inputId}
        name={field.key}
        value={typeof value === "number" ? value : null}
        onValueChange={onChange}
        integer={field.integer}
        aria-describedby={[field.unit ? unitId : "", describedBy ?? ""].filter(Boolean).join(" ") || undefined}
        invalid={invalid}
        disabled={disabled}
      />
    </WithUnit>
  );
}

export function SliderControl({ field, value, onChange, inputId, describedBy, disabled }: ControlProps) {
  const n = typeof value === "number" ? value : 0;
  return (
    <span className={`${styles.subRow} ${styles.slider}`}>
      <RangeInput
        id={inputId}
        name={field.key}
        min={field.min ?? 0}
        max={field.max ?? 100}
        step={field.step ?? (field.integer ? 1 : 0.1)}
        value={n}
        onValueChange={onChange}
        aria-describedby={describedBy}
        aria-valuetext={`${formatNumber(n)}${field.unit ? ` ${field.unit}` : ""}`}
        disabled={disabled}
      />
      <span className={`${styles.weightValue} ${styles.num}`} aria-hidden="true">
        {formatNumber(n)}
      </span>
    </span>
  );
}

export function selectOptions(field: { options: unknown[]; default: unknown; recommended: boolean }, value: unknown) {
  const opts = field.options.map((o) => ({
    value: String(o),
    label: `${optionLabel(o)}${field.recommended && equal(o, field.default) ? " (Recommended)" : ""}`,
  }));
  if (value === null || value === undefined) opts.unshift({ value: "", label: "Not set" });
  return opts;
}

export function SelectControl({ field, value, onChange, inputId, describedBy, invalid, disabled }: ControlProps) {
  return (
    <SelectInput
      id={inputId}
      name={field.key}
      value={value === null || value === undefined ? "" : String(value)}
      onValueChange={(v) => {
        const match = field.options.find((o) => String(o) === v);
        onChange(match === undefined ? v : match);
      }}
      options={selectOptions(field, value)}
      aria-describedby={describedBy}
      invalid={invalid}
      disabled={disabled}
    />
  );
}

export function TextControl({ field, value, onChange, inputId, describedBy, invalid, disabled }: ControlProps) {
  return (
    <TextInput
      id={inputId}
      name={field.key}
      value={value === null || value === undefined ? "" : String(value)}
      onValueChange={(v) => onChange(v === "" && field.nullable ? null : v)}
      placeholder={field.nullable ? "Not set" : undefined}
      aria-describedby={describedBy}
      invalid={invalid}
      readOnly={disabled}
    />
  );
}

export function TimeControl({ field, value, onChange, inputId, describedBy, invalid, disabled }: ControlProps) {
  return (
    <TimeInput
      id={inputId}
      name={field.key}
      value={typeof value === "string" ? value : ""}
      onValueChange={onChange}
      aria-describedby={describedBy}
      invalid={invalid}
      disabled={disabled}
    />
  );
}

export function TagsControl({ field, value, onChange, inputId, describedBy, invalid, disabled }: ControlProps) {
  const list = Array.isArray(value) ? value.map(String) : [];
  return (
    <TagEditor
      label={field.label}
      values={list}
      onValuesChange={onChange}
      options={field.options.map(String)}
      strict={field.strict_options && field.options.length > 0}
      format={field.options.length ? optionLabel : undefined}
      disabled={disabled}
      invalid={invalid}
      describedBy={describedBy}
      inputId={inputId}
    />
  );
}
