import { useId, useState, type FormEvent } from "react";
import { Button } from "../../kit/Button";
import { STATUSES, describeCode } from "../../kit/labels";
import { Sheet } from "../../kit/Sheet";
import styles from "./Pipeline.module.css";

interface StatusChooserProps {
  company: string;
  target: string;
  statuses: string[];
  onChoose: (status: string) => void;
  onClose: () => void;
}

/** A column holds several statuses (Queued = queued + prepared): ask which one before moving. */
export function StatusChooser({ company, target, statuses, onChoose, onClose }: StatusChooserProps) {
  const [value, setValue] = useState(statuses[0] ?? "");
  const formId = useId();
  function submit(e: FormEvent) {
    e.preventDefault();
    if (value) onChoose(value);
  }
  return (
    <Sheet
      open
      title={`Move ${company} to ${target}`}
      closeLabel="Cancel"
      onClose={onClose}
      footer={
        <Button type="submit" form={formId} variant="primary">
          Move
        </Button>
      }
    >
      <form id={formId} onSubmit={submit}>
        <fieldset className={styles.choices}>
          <legend className={styles.legend}>This column holds more than one status. Which one?</legend>
          {statuses.map((s) => (
            <label key={s} className={styles.choice}>
              <input
                type="radio"
                name="status"
                value={s}
                checked={value === s}
                onChange={() => setValue(s)}
                data-autofocus={value === s || undefined}
              />
              {describeCode(STATUSES, s).label}
            </label>
          ))}
        </fieldset>
      </form>
    </Sheet>
  );
}
