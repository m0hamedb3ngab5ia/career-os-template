import { useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import { Button } from "../../kit/Button";
import { TextField } from "../../kit/FormField";
import { Sheet } from "../../kit/Sheet";
import { useToast } from "../../kit/Toast";
import styles from "./ActionItems.module.css";
import { useSetDue } from "./api";
import { dueValue } from "./dueValue";
import type { ActionItem } from "./types";

/** "Add date": a real deadline the candidate knows about (never invented), with why it matters. */
export function DueSheet({ item, onClose }: { item: ActionItem; onClose: () => void }) {
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [reason, setReason] = useState("");
  const setDue = useSetDue();
  const toast = useToast();
  const name = item.company || item.what;

  function submit(e: FormEvent) {
    e.preventDefault();
    const due = dueValue(date, time);
    if (!due) return;
    setDue.mutate(
      { id: item.id, due, due_reason: reason.trim() || null },
      {
        onSuccess: () => {
          toast.show({ message: `Date added for ${name}` });
          onClose();
        },
      },
    );
  }

  return (
    <Sheet
      title="Add date"
      description={`When is ${name} due? Only add a date the posting, email or form actually gives.`}
      onClose={onClose}
    >
      <form onSubmit={submit} className={styles.form}>
        <div className={styles.row2}>
          <TextField label="Date" type="date" name="due-date" autoComplete="off" required value={date} onChange={(e) => setDate(e.target.value)} />
          <TextField label="Time (optional)" type="time" name="due-time" autoComplete="off" value={time} onChange={(e) => setTime(e.target.value)} />
        </div>
        <TextField
          label="Why this date (optional)"
          name="due-reason"
          autoComplete="off"
          placeholder="posting closes…"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        {setDue.error ? (
          <p role="alert" className={styles.error}>
            {setDue.error instanceof ApiError ? setDue.error.message : "Couldn't save the date."}
          </p>
        ) : null}
        <div className={styles.formButtons}>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" pending={setDue.isPending} pendingLabel="Saving…" >
            Save date
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
