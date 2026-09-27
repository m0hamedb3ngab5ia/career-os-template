import type { FieldSchema } from "../types";

export interface ControlProps<V = unknown> {
  field: FieldSchema;
  value: V;
  onChange: (v: unknown) => void;
  /** Id of the control's first focusable element: the row's <label htmlFor> points here. */
  inputId: string;
  /** Hint and error ids for aria-describedby. */
  describedBy?: string;
  invalid: boolean;
  disabled: boolean;
}
