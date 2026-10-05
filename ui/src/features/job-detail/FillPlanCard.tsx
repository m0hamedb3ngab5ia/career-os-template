import { useState } from "react";
import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import { SelectInput, TextInput } from "../../kit/inputs";
import { useToast } from "../../kit/Toast";
import { errorText, useEditFillField, useFillPlan, useMakeFillPlan, type FillField } from "./api";
import { Card } from "./Card";
import styles from "./JobDetail.module.css";

// Where each value came from, in plain words (REQ-105: saved answer | résumé | default | yours).
export function sourceLabel(f: FillField): string {
  const s = f.source ?? "";
  if (f.skipped) return "Skipped";
  if (s.startsWith("standard:") || s === "eeo") return "Saved answer";
  if (s === "profile" || s === "file") return "Résumé / profile";
  if (s === "user") return "Edited by you";
  if (s === "pause:sensitive") return "Never filled (sensitive)";
  if (s.startsWith("pause:")) return `Your answer needed (${s.slice(6)})`;
  if (s === "unanswered") return "Needs input";
  return f.value == null ? "Empty" : "Default";
}

const shown = (v: unknown) => (Array.isArray(v) ? v.join(", ") : v == null ? "" : String(v));

function FieldRow({ jobId, f }: { jobId: string; f: FillField }) {
  const edit = useEditFillField(jobId, f.field_id);
  const toast = useToast();
  const [value, setValue] = useState(shown(f.value));
  const [save, setSave] = useState(true);
  const editable = !["file", "hidden"].includes(f.type) && f.source !== "pause:sensitive";
  const eeo = f.source === "eeo" || f.source === "pause:eeo";
  const empty = f.value == null || shown(f.value) === "";
  function send(body: { value?: string; skip?: boolean; save?: boolean }) {
    edit.mutate(body, {
      onSuccess: (r) =>
        toast.show({ message: body.skip ? `Skipped: ${f.label}` : `Saved: ${f.label}${r.saved ? ", also saved to your profile" : ""}` }),
      onError: (e) => toast.show({ message: errorText(e) }),
    });
  }
  return (
    <tr data-needs={empty && !f.skipped ? "" : undefined}>
      <th scope="row">{f.label}</th>
      <td>
        {!editable ? (
          shown(f.value) || "—"
        ) : f.options?.length ? (
          <SelectInput
            aria-label={f.label}
            value={value}
            onValueChange={setValue}
            options={[{ value: "", label: "Choose…" }, ...f.options.map((o) => ({ value: o, label: o }))]}
          />
        ) : (
          <TextInput aria-label={f.label} value={value} onValueChange={setValue} />
        )}
      </td>
      <td>{sourceLabel(f)}</td>
      <td>{f.required ? <Chip tone="orange">Required</Chip> : "Optional"}</td>
      <td>
        {editable ? (
          <>
            {!eeo ? (
              <label>
                <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} /> Save to profile
              </label>
            ) : null}{" "}
            <Button
              disabled={edit.isPending || !value.trim() || value === shown(f.value)}
              onClick={() => send({ value, save: save && !eeo })}
            >
              Save
            </Button>
            {!f.required && empty && !f.skipped ? (
              <Button disabled={edit.isPending} onClick={() => send({ skip: true })}>
                Skip
              </Button>
            ) : null}
          </>
        ) : null}
      </td>
    </tr>
  );
}

/** Preview fill: every field career-os will type, editable; unknown ones asked; Fill waits for required answers. */
export function FillPlanCard({ jobId }: { jobId: string }) {
  const q = useFillPlan(jobId);
  const make = useMakeFillPlan(jobId);
  const toast = useToast();
  const plan = q.data?.plan;
  const problems = q.data?.problems ?? [];
  const preview = (
    <Button disabled={make.isPending} onClick={() => make.mutate(undefined, { onError: (e) => toast.show({ message: errorText(e) }) })}>
      {make.isPending ? "Building preview…" : plan ? "Rebuild preview" : "Preview fill"}
    </Button>
  );
  return (
    <Card title="Fill preview" aside={plan ? (problems.length ? <Chip tone="orange">{problems.length} to answer</Chip> : <Chip tone="green">Ready to fill</Chip>) : null}>
      {!plan ? (
        <p>See what career-os will type into the application, and answer anything it doesn't know, before it fills. {preview}</p>
      ) : (
        <>
          <div role="status" aria-live="polite">
            {problems.length ? (
              <p className={styles.alert}>Fill application waits until you answer: {problems.map((p) => p.replace(/^[^)]*\): /, "")).join("; ")}</p>
            ) : null}
          </div>
          <div className={styles.planWrap}>
          <table className={styles.planTable}>
            <caption className="sr-only">Fields career-os will fill</caption>
            <thead>
              <tr>
                <th scope="col">Field</th>
                <th scope="col">Value</th>
                <th scope="col">Source</th>
                <th scope="col">Required</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {plan.fields
                .filter((f) => f.type !== "hidden")
                .map((f) => (
                  <FieldRow key={`${f.field_id}:${shown(f.value)}:${f.skipped ? 1 : 0}`} jobId={jobId} f={f} />
                ))}
            </tbody>
          </table>
          </div>
          {preview}
        </>
      )}
    </Card>
  );
}
