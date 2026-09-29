import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";
import { useState, type ComponentProps } from "react";
import { TierBadge } from "../../../kit/chips";
import { NumberInput, SelectInput, TagEditor, TextInput, TimeInput } from "../../../kit/inputs";
import { Switch } from "../../../kit/Switch";
import { humanize, reasonLabel } from "../format";
import styles from "../settings.module.css";
import type { ControlProps } from "./types";

// Editors for list- and map-shaped settings: tier rules, token rules, time ranges, check levels, name → value
// maps and tables of records.

type Rule = { if: string; tier: string };

function move<T>(list: T[], i: number, by: number): T[] {
  const j = i + by;
  if (j < 0 || j >= list.length) return list;
  const out = [...list];
  [out[i], out[j]] = [out[j]!, out[i]!];
  return out;
}

/** targets.yaml tier_rules: ordered {if, tier} rows, first match wins. */
function TierRules({ field, value, onChange, inputId, describedBy, invalid, disabled }: ControlProps) {
  const rules: Rule[] = Array.isArray(value) ? (value as Rule[]) : [];
  const set = (i: number, patch: Partial<Rule>) => onChange(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <>
      <ol className={styles.subList} aria-label={field.label}>
        {rules.map((r, i) => (
          <li key={i} className={styles.subRow}>
            <TextInput
              id={i === 0 ? inputId : undefined}
              className={styles.codeInput}
              aria-label={`Rule ${i + 1} condition`}
              aria-describedby={describedBy}
              translate="no"
              value={r.if}
              onValueChange={(v) => set(i, { if: v })}
              invalid={invalid}
              readOnly={disabled}
            />
            <SelectInput
              aria-label={`Rule ${i + 1} tier`}
              value={r.tier}
              onValueChange={(v) => set(i, { tier: v })}
              options={["A", "B", "C"].map((t) => ({ value: t, label: `Tier ${t}` }))}
              disabled={disabled}
            />
            <TierBadge tier={r.tier} />
            <button type="button" className={styles.iconButton} aria-label={`Move rule ${i + 1} up`}
              disabled={disabled || i === 0} onClick={() => onChange(move(rules, i, -1))}>
              <ArrowUp size={14} aria-hidden="true" />
            </button>
            <button type="button" className={styles.iconButton} aria-label={`Move rule ${i + 1} down`}
              disabled={disabled || i === rules.length - 1} onClick={() => onChange(move(rules, i, 1))}>
              <ArrowDown size={14} aria-hidden="true" />
            </button>
            <button type="button" className={styles.iconButton} aria-label={`Remove rule ${i + 1}`}
              disabled={disabled} onClick={() => onChange(rules.filter((_, j) => j !== i))}>
              <X size={14} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ol>
      {disabled ? null : (
        <button type="button" className={styles.addButton} onClick={() => onChange([...rules, { if: "fit >= 70", tier: "C" }])}>
          <Plus size={14} aria-hidden="true" />
          Add tier rule
        </button>
      )}
    </>
  );
}

/** rule_list: token lists (runs.auto_submit.allow / manual) or ordered {if, tier} rows (tier_rules). */
export function RuleListControl(props: ControlProps) {
  const sample = Array.isArray(props.value) && props.value.length ? props.value[0] : Array.isArray(props.field.default) ? props.field.default[0] : null;
  if (sample && typeof sample === "object") return <TierRules {...props} />;
  const list = Array.isArray(props.value) ? props.value.map(String) : [];
  return (
    <TagEditor
      label={props.field.label}
      values={list}
      onValuesChange={props.onChange}
      disabled={props.disabled}
      invalid={props.invalid}
      describedBy={props.describedBy}
      inputId={props.inputId}
      tone="gray"
    />
  );
}

/** schedule.quiet_hours: on/off (null = off) and a start and end time. */
export function TimeRangeControl({ field, value, onChange, inputId, describedBy, invalid, disabled }: ControlProps) {
  const range = value && typeof value === "object" ? (value as { start: string; end: string }) : null;
  const fallback = (field.default as { start: string; end: string } | null) ?? { start: "09:00", end: "18:00" };
  return (
    <span className={styles.subRow}>
      {field.nullable ? (
        <Switch
          checked={range !== null}
          onCheckedChange={(on) => onChange(on ? fallback : null)}
          label={field.label}
          labelHidden
          describedBy={describedBy}
          disabled={disabled}
        />
      ) : null}
      {range ? (
        <>
          <TimeInput id={inputId} aria-label={`${field.label} start`} value={range.start}
            onValueChange={(v) => onChange({ ...range, start: v })} invalid={invalid} disabled={disabled} />
          <span aria-hidden="true">–</span>
          <TimeInput aria-label={`${field.label} end`} value={range.end}
            onValueChange={(v) => onChange({ ...range, end: v })} invalid={invalid} disabled={disabled} />
        </>
      ) : (
        <span className={styles.hint}>Off</span>
      )}
    </span>
  );
}

const LEVELS = ["block", "skip", "review", "info", "off"];

/** safety.levels: one row per check code; "Built-in level" leaves the code out of the map. */
export function ReasonLevelsControl({ field, value, onChange, describedBy, disabled }: ControlProps) {
  const map = value && typeof value === "object" ? (value as Record<string, string>) : {};
  return (
    <ul className={styles.subList} aria-label={field.label} aria-describedby={describedBy}>
      {field.options.map((o) => {
        const code = String(o);
        const label = reasonLabel(code);
        return (
          <li key={code} className={`${styles.subRow} ${styles.spread}`}>
            <span>
              <span className={styles.rowLabel}>{label}</span>
              <span className={`${styles.code} ${styles.block}`} translate="no">
                {code}
              </span>
            </span>
            <SelectInput
              aria-label={`Level for ${label}`}
              value={map[code] ?? ""}
              onValueChange={(lv) => {
                const next = { ...map };
                if (lv) next[code] = lv;
                else delete next[code];
                onChange(next);
              }}
              options={[
                { value: "", label: "Built-in level (Recommended)" },
                ...LEVELS.map((l) => ({ value: l, label: humanize(l) })),
              ]}
              disabled={disabled}
            />
          </li>
        );
      })}
    </ul>
  );
}

function parseCell(raw: string, like: unknown): unknown {
  if (Array.isArray(like)) {
    return raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }
  if (typeof like === "number") {
    const n = Number(raw.trim());
    return raw.trim() === "" || Number.isNaN(n) ? raw : n;
  }
  return raw;
}

function showCell(v: unknown): string {
  if (Array.isArray(v)) return v.join(", ");
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** A text cell that keeps what you type ("found, ") while it has focus and reports the parsed value. */
function CellInput({
  value,
  onText,
  ...rest
}: Omit<ComponentProps<typeof TextInput>, "value" | "onValueChange"> & { value: unknown; onText: (t: string) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <TextInput
      {...rest}
      value={draft ?? showCell(value)}
      onValueChange={(t) => {
        setDraft(t);
        onText(t);
      }}
      onBlur={() => setDraft(null)}
    />
  );
}

/** key_value: name → value rows (month → multiplier, company → domain(s)). Lists are comma-separated. */
export function KeyValueControl({ field, value, onChange, inputId, describedBy, invalid, disabled }: ControlProps) {
  const map = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  const entries = Object.entries(map);
  const sampleValue = entries[0]?.[1] ?? Object.values((field.default as object) ?? {})[0];
  const numeric = typeof sampleValue === "number";
  if (disabled) {
    return (
      <dl className={styles.subList} aria-describedby={describedBy}>
        {entries.map(([k, v]) => (
          <div key={k} className={styles.subRow}>
            <dt className={styles.rowLabel}>{humanize(k)}</dt>
            <dd className={`${styles.hint} ${styles.flush}`}>
              {v && typeof v === "object" && !Array.isArray(v)
                ? Object.entries(v as Record<string, unknown>).map(([a, b]) => `${humanize(a)} ${showCell(b)}`).join(" · ")
                : showCell(v)}
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  const rename = (from: string, to: string) =>
    onChange(Object.fromEntries(entries.map(([k, v]) => (k === from ? [to, v] : [k, v]))));
  return (
    <>
      <ul className={styles.subList} aria-label={field.label}>
        {entries.map(([k, v], i) => (
          <li key={i} className={styles.subRow}>
            <TextInput id={i === 0 ? inputId : undefined} aria-label={`Name ${i + 1}`} aria-describedby={describedBy}
              value={k} onValueChange={(nk) => rename(k, nk)} invalid={invalid} />
            <span aria-hidden="true">→</span>
            {numeric ? (
              <NumberInput aria-label={`Value for ${k || `row ${i + 1}`}`} value={typeof v === "number" ? v : null}
                onValueChange={(n) => onChange({ ...map, [k]: n })} invalid={invalid} />
            ) : (
              <CellInput aria-label={`Value for ${k || `row ${i + 1}`}`} value={v}
                onText={(t) => onChange({ ...map, [k]: t.includes(",") ? parseCell(t, []) : t })} invalid={invalid} />
            )}
            <button type="button" className={styles.iconButton} aria-label={`Remove ${k || `row ${i + 1}`}`}
              onClick={() => onChange(Object.fromEntries(entries.filter(([x]) => x !== k)))}>
              <X size={14} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className={styles.addButton}
        onClick={() => {
          let n = entries.length + 1;
          while (`new${n}` in map) n += 1;
          onChange({ ...map, [`new${n}`]: numeric ? 1 : "" });
        }}
      >
        <Plus size={14} aria-hidden="true" />
        Add row
      </button>
    </>
  );
}

// Columns for record lists that may start empty (the example boards have these keys).
const RECORD_COLUMNS: Record<string, string[]> = {
  "companies:boards": ["company", "ats", "slug", "url"],
};

/** records: a small table, one row per record; list cells are comma-separated. */
export function RecordsControl({ field, value, onChange, inputId, describedBy, invalid, disabled }: ControlProps) {
  const rows = Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
  const defaults = Array.isArray(field.default) ? (field.default as Record<string, unknown>[]) : [];
  const cols = [...new Set([...(RECORD_COLUMNS[field.id] ?? []), ...[...rows, ...defaults].flatMap((r) => Object.keys(r))])];
  const like = (c: string) => [...rows, ...defaults].map((r) => r[c]).find((v) => v !== undefined && v !== null);
  const setCell = (i: number, c: string, raw: string) =>
    onChange(
      rows.map((r, j) => {
        if (j !== i) return r;
        const next = { ...r, [c]: parseCell(raw, like(c)) };
        if (raw === "" && !Array.isArray(like(c))) delete next[c];
        return next;
      }),
    );
  return (
    <>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-describedby={describedBy}>
          <caption className="sr-only">{field.label}</caption>
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c} scope="col">
                  {humanize(c)}
                </th>
              ))}
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {cols.map((c, ci) => (
                  <td key={c}>
                    <CellInput
                      id={i === 0 && ci === 0 ? inputId : undefined}
                      aria-label={`${humanize(c)}, row ${i + 1}`}
                      value={r[c]}
                      onText={(t) => setCell(i, c, t)}
                      readOnly={disabled}
                      invalid={invalid}
                    />
                  </td>
                ))}
                <td>
                  {disabled ? null : (
                    <span className={`${styles.subRow} ${styles.nowrap}`}>
                      <button type="button" className={styles.iconButton} aria-label={`Move row ${i + 1} up`}
                        disabled={i === 0} onClick={() => onChange(move(rows, i, -1))}>
                        <ArrowUp size={14} aria-hidden="true" />
                      </button>
                      <button type="button" className={styles.iconButton} aria-label={`Remove row ${i + 1}`}
                        onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                        <X size={14} aria-hidden="true" />
                      </button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {disabled ? null : (
        <button type="button" className={styles.addButton} onClick={() => onChange([...rows, {}])}>
          <Plus size={14} aria-hidden="true" />
          Add row
        </button>
      )}
    </>
  );
}
