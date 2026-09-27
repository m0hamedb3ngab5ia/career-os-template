import { createContext, use, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { equal } from "./format";
import type { FieldSchema, SectionData, Values } from "./types";
import { isPolicy } from "./types";

// One Settings page's form state. The provider is the only place that knows how drafts are kept: components
// read `value(id)` and call `set(id, v)`. A draft equal to the saved value is not a change.

export interface SettingsForm {
  data: SectionData;
  fields: FieldSchema[];
  field: (id: string) => FieldSchema | undefined;
  value: (id: string) => unknown;
  set: (id: string, v: unknown) => void;
  setMany: (values: Values) => void;
  /** {field id: draft} for every real change, in schema order. */
  changes: Values;
  dirtyCount: number;
  errors: Record<string, string>;
  general: string[];
  setErrors: (fields: Record<string, string>, general?: string[]) => void;
  discard: () => void;
  /** The version the first unsaved edit was made against; a save sends it so a change on disk since then is a
   * 409, even after a refetch brought a newer version. Null when there are no drafts. */
  baseVersion: string | null;
}

const FormContext = createContext<SettingsForm | null>(null);

export function useSettingsForm(): SettingsForm {
  const f = use(FormContext);
  if (!f) throw new Error("useSettingsForm must be used inside SettingsFormProvider");
  return f;
}

/** Plain-language checks the browser can make before any request: a number field left empty or not a number. */
export function clientErrors(fields: FieldSchema[], changes: Values): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of fields) {
    if (!(f.id in changes)) continue;
    const v = changes[f.id];
    if (typeof v === "number" && Number.isNaN(v)) out[f.id] = "Enter a number.";
    else if (v === null && !f.nullable) out[f.id] = "A value is required.";
  }
  return out;
}

export function SettingsFormProvider({ data, children }: { data: SectionData; children: ReactNode }) {
  const [drafts, setDrafts] = useState<Values>({});
  const [errors, setErrorState] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string[]>([]);
  const [baseVersion, setBaseVersion] = useState<string | null>(null);

  const fields = useMemo(
    () => data.section.groups.flatMap((g) => g.items.filter((i): i is FieldSchema => !isPolicy(i))),
    [data.section],
  );
  const byId = useMemo(() => new Map(fields.map((f) => [f.id, f])), [fields]);

  const changes = useMemo(() => {
    const out: Values = {};
    for (const f of fields) {
      if (f.id in drafts && !equal(drafts[f.id], data.values[f.id])) out[f.id] = drafts[f.id];
    }
    return out;
  }, [fields, drafts, data.values]);

  // Every field back to its original value: the form is clean again, so drop the conflict baseline.
  const dirty = Object.keys(changes).length > 0;
  useEffect(() => {
    if (!dirty) setBaseVersion(null);
  }, [dirty]);

  const clearError = useCallback((ids: string[]) => {
    setErrorState((e) => {
      if (!ids.some((id) => id in e)) return e;
      const next = { ...e };
      for (const id of ids) delete next[id];
      return next;
    });
    setGeneral([]);
  }, []);

  const set = useCallback(
    (id: string, v: unknown) => {
      setDrafts((d) => ({ ...d, [id]: v }));
      setBaseVersion((b) => b ?? data.version);
      clearError([id]);
    },
    [clearError, data.version],
  );

  const setMany = useCallback(
    (values: Values) => {
      setDrafts((d) => ({ ...d, ...values }));
      setBaseVersion((b) => b ?? data.version);
      clearError(Object.keys(values));
    },
    [clearError, data.version],
  );

  const setErrors = useCallback((f: Record<string, string>, g: string[] = []) => {
    setErrorState(f);
    setGeneral(g);
  }, []);

  const discard = useCallback(() => {
    setDrafts({});
    setBaseVersion(null);
    setErrorState({});
    setGeneral([]);
  }, []);

  const value = useCallback((id: string) => (id in drafts ? drafts[id] : data.values[id]), [drafts, data.values]);

  const api = useMemo<SettingsForm>(
    () => ({
      data,
      fields,
      field: (id) => byId.get(id),
      value,
      set,
      setMany,
      changes,
      dirtyCount: Object.keys(changes).length,
      errors,
      general,
      setErrors,
      discard,
      baseVersion,
    }),
    [data, fields, byId, value, set, setMany, changes, errors, general, setErrors, discard, baseVersion],
  );

  return <FormContext value={api}>{children}</FormContext>;
}
