import { Plus, X } from "lucide-react";
import { NumberInput, SelectInput, TimeInput, WithUnit } from "../../../kit/inputs";
import { Switch } from "../../../kit/Switch";
import { useSettingsForm } from "../form";
import { optionLabel } from "../format";
import styles from "../settings.module.css";
import type { ControlProps } from "./types";

type Mode = "every_hours" | "every_days" | "at";
type Job = Record<string, unknown> & { enabled?: boolean; preset?: string | null };

const WHEN_KEYS: Mode[] = ["every_hours", "every_days", "at"];
const MODE_LABEL: Record<Mode, string> = { every_hours: "Every N hours", every_days: "Every N days", at: "At set times" };
// score / prepare rows take an optional budget preset (schedule.jobs.<kind>.preset)
const PRESET_KINDS = new Set(["score", "prepare"]);

function modeOf(job: Job): Mode {
  return WHEN_KEYS.find((k) => k in job) ?? "every_hours";
}

function withoutWhen(job: Job): Job {
  const out: Job = {};
  for (const [k, v] of Object.entries(job)) if (!WHEN_KEYS.includes(k as Mode)) out[k] = v;
  return out;
}

/** One schedule.jobs.<kind> block: on/off, every N hours / days or times of day, and for score and prepare an
 * optional budget preset. Keys the form doesn't show (mcp_servers, allowed_tools_extra) are kept as they are. */
export function ScheduleControl({ field, value, onChange, inputId, describedBy, invalid, disabled }: ControlProps) {
  const form = useSettingsForm();
  const job: Job = value && typeof value === "object" ? (value as Job) : {};
  const mode = modeOf(job);
  const kind = field.key.split(".").at(-1) ?? "";
  const enabled = job.enabled !== false;
  const presetNames = (form.field("pipeline:runs.preset")?.options ?? []).map(String);
  const times = Array.isArray(job.at) ? (job.at as string[]) : [];

  const update = (patch: Job) => onChange({ ...job, ...patch });
  const setMode = (m: Mode) =>
    onChange({ ...withoutWhen(job), [m]: m === "at" ? ["01:00"] : m === "every_days" ? 1 : 3 });

  return (
    <span className={styles.subRow}>
      <Switch
        checked={enabled}
        onCheckedChange={(on) => update({ enabled: on })}
        label={`${field.label} schedule`}
        labelHidden
        describedBy={describedBy}
        disabled={disabled}
      />
      <SelectInput
        id={inputId}
        aria-label={`${field.label}: how often`}
        value={mode}
        onValueChange={(m) => setMode(m as Mode)}
        options={WHEN_KEYS.map((m) => ({ value: m, label: MODE_LABEL[m] }))}
        disabled={disabled}
        invalid={invalid}
      />
      {mode === "at" ? (
        <>
          {times.map((t, i) => (
            <span key={i} className={styles.subRow}>
              <TimeInput
                aria-label={`${field.label}: time ${i + 1}`}
                value={t}
                onValueChange={(v) => update({ at: times.map((x, j) => (j === i ? v : x)) })}
                disabled={disabled}
                invalid={invalid}
              />
              {times.length > 1 ? (
                <button
                  type="button"
                  className={styles.iconButton}
                  aria-label={`Remove ${t || `time ${i + 1}`} from ${field.label}`}
                  onClick={() => update({ at: times.filter((_, j) => j !== i) })}
                  disabled={disabled}
                >
                  <X size={14} aria-hidden="true" />
                </button>
              ) : null}
            </span>
          ))}
          <button
            type="button"
            className={styles.iconButton}
            aria-label={`Add a time to ${field.label}`}
            onClick={() => update({ at: [...times, "12:00"] })}
            disabled={disabled}
          >
            <Plus size={14} aria-hidden="true" />
          </button>
        </>
      ) : (
        <WithUnit unit={mode === "every_hours" ? "hours" : "days"}>
          <NumberInput
            aria-label={`${field.label}: every how many ${mode === "every_hours" ? "hours" : "days"}`}
            value={typeof job[mode] === "number" ? (job[mode] as number) : null}
            onValueChange={(n) => update({ [mode]: n })}
            integer
            disabled={disabled}
            invalid={invalid}
          />
        </WithUnit>
      )}
      {PRESET_KINDS.has(kind) && presetNames.length ? (
        <SelectInput
          aria-label={`${field.label}: budget`}
          value={job.preset ?? ""}
          onValueChange={(p) => {
            if (p) return update({ preset: p });
            const rest = { ...job };
            delete rest.preset;
            onChange(rest);
          }}
          options={[
            { value: "", label: "Runs budget (Recommended)" },
            ...presetNames.map((p) => ({ value: p, label: optionLabel(p) })),
          ]}
          disabled={disabled}
        />
      ) : null}
    </span>
  );
}
