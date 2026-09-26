import { useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import { useMeta } from "../../api/queries";
import { Button } from "../../kit/Button";
import { SelectField, TextField } from "../../kit/FormField";
import { ACTION_TYPES, NEEDS, PRIORITIES, describeCode } from "../../kit/labels";
import { Sheet } from "../../kit/Sheet";
import { useToast } from "../../kit/Toast";
import styles from "./ActionItems.module.css";
import { useAddItem } from "./api";
import { dueValue } from "./dueValue";

const FALLBACK = { action_types: ["other"], action_needs: ["laptop", "phone", "anytime"], priorities: ["H", "M", "L"] };

/** "Add item": a to-do the candidate writes themselves; the same fields as `careeros action add`. */
export function AddItemSheet({ onClose }: { onClose: () => void }) {
  const meta = useMeta().data ?? FALLBACK;
  const add = useAddItem();
  const toast = useToast();
  const [f, setF] = useState({
    what: "", type: "other", needs: "anytime", priority: "M", company: "", role: "", link: "", date: "", time: "", reason: "",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));

  function submit(e: FormEvent) {
    e.preventDefault();
    const due = dueValue(f.date, f.time);
    add.mutate(
      {
        what: f.what.trim(), type: f.type, needs: f.needs, priority: f.priority, company: f.company.trim(),
        role: f.role.trim(), link: f.link.trim(), due, due_reason: due ? f.reason.trim() || null : null,
      },
      {
        onSuccess: () => {
          toast.show({ message: "Item added" });
          onClose();
        },
      },
    );
  }

  const opts = (codes: string[], table: typeof ACTION_TYPES) => codes.map((c) => ({ value: c, label: describeCode(table, c).label }));
  return (
    <Sheet title="Add item" description="Something only you can do. It shows here and on Today." onClose={onClose}>
      <form onSubmit={submit} className={styles.form}>
        <TextField label="What to do" name="what" required autoComplete="off" value={f.what} onChange={set("what")} />
        <div className={styles.row2}>
          <TextField label="Company (optional)" name="company" autoComplete="off" value={f.company} onChange={set("company")} />
          <TextField label="Role (optional)" name="role" autoComplete="off" value={f.role} onChange={set("role")} />
        </div>
        <TextField
          label="Link (optional)"
          name="link"
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="https://…"
          value={f.link}
          onChange={set("link")}
        />
        <div className={styles.row2}>
          <SelectField label="Type" name="type" value={f.type} onChange={set("type")} options={opts(meta.action_types, ACTION_TYPES)} />
          <SelectField label="Priority" name="priority" value={f.priority} onChange={set("priority")} options={opts(meta.priorities, PRIORITIES)} />
          <SelectField label="Needs" name="needs" value={f.needs} onChange={set("needs")} options={opts(meta.action_needs, NEEDS)} />
        </div>
        <div className={styles.row2}>
          <TextField label="Due date (optional)" name="due-date" type="date" autoComplete="off" value={f.date} onChange={set("date")} />
          <TextField label="Time (optional)" name="due-time" type="time" autoComplete="off" value={f.time} onChange={set("time")} disabled={!f.date} />
        </div>
        {f.date ? (
          <TextField label="Why this date (optional)" name="due-reason" autoComplete="off" placeholder="posting closes…" value={f.reason} onChange={set("reason")} />
        ) : null}
        {add.error ? (
          <p role="alert" className={styles.error}>
            {add.error instanceof ApiError ? add.error.message : "Couldn't add the item."}
          </p>
        ) : null}
        <div className={styles.formButtons}>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" pending={add.isPending} pendingLabel="Adding…" >
            Add item
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
