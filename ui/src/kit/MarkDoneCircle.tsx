import { Check } from "lucide-react";
import styles from "./controls.module.css";

interface MarkDoneCircleProps {
  done: boolean;
  onDoneChange: (done: boolean) => void;
  /** Names the item in the accessible label: "Mark {itemName} done". */
  itemName: string;
}

export function MarkDoneCircle({ done, onDoneChange, itemName }: MarkDoneCircleProps) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={done}
      aria-label={`Mark ${itemName} done`}
      className={styles.done}
      onClick={() => onDoneChange(!done)}
    >
      <span className={styles.doneRing} aria-hidden="true">
        {done ? <Check size={13} strokeWidth={2.5} /> : null}
      </span>
    </button>
  );
}
