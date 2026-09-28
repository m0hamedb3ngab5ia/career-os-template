import { Filter } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Button } from "../../kit/Button";
import { TextInput } from "../../kit/inputs";
import { humanize } from "../../kit/labels";
import { Popover } from "../../kit/Popover";
import { useJobFacets, type FilterParams } from "./api";
import type { Column } from "./cells";
import styles from "./JobsPage.module.css";
import { FILTERS, sortDirection, type ColumnFilter, type FilterField } from "./urlState";

/** Column values that read better humanized (status codes, verdicts); everything else is shown as stored. */
const CODE_FIELDS = new Set<FilterField>(["status", "safety", "category"]);

export function facetLabel(field: FilterField, value: string): string {
  if (field === "qa_passed") return value === "1" ? "Passed" : "Failed";
  return CODE_FIELDS.has(field) ? humanize(value) : value;
}

/** "queued, applied", "≥ 80", "80–90", "2026-01-01 – 2026-02-01". */
export function filterSummary(field: FilterField, f: ColumnFilter): string {
  if (f.kind === "values") return f.values.map((v) => facetLabel(field, v)).join(", ");
  if (f.min && f.max) return `${f.min} – ${f.max}`;
  return f.min ? `≥ ${f.min}` : `≤ ${f.max}`;
}

interface Props {
  col: Column;
  filter: ColumnFilter | undefined;
  onChange: (field: FilterField, f: ColumnFilter | null) => void;
  /** Every other active filter, for the value counts. */
  params: FilterParams;
  sort: string;
  onSortTo: (sort: string) => void;
}

/** Excel-style header menu: sort, a searchable checklist of the column's values with counts, or a min..max
 *  range; Apply writes the filter to the URL, Clear removes it. */
export function HeaderFilterMenu({ col, filter, onChange, params, sort, onSortTo }: Props) {
  const field = col.filter!;
  const kind = FILTERS[field].kind;
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);
  const id = useId();
  const close = useCallback(() => setOpen(false), []);

  // Draft state, reset from the applied filter each time the menu opens.
  const [picked, setPicked] = useState<Set<string>>(() => new Set());
  const [min, setMin] = useState("");
  const [max, setMax] = useState("");
  const filterRef = useRef(filter);
  filterRef.current = filter;
  useEffect(() => {
    if (!open) return;
    const f = filterRef.current;
    setPicked(new Set(f?.kind === "values" ? f.values : []));
    setMin(f?.kind === "range" ? f.min : "");
    setMax(f?.kind === "range" ? f.max : "");
    // Reset the draft only when the menu opens, not on every URL-driven `filter` change while it's open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function apply() {
    if (kind === "values") onChange(field, picked.size ? { kind: "values", values: [...picked] } : null);
    else onChange(field, min.trim() || max.trim() ? { kind: "range", min: min.trim(), max: max.trim() } : null);
    setOpen(false);
    anchor.current?.focus();
  }
  function clear() {
    onChange(field, null);
    setOpen(false);
    anchor.current?.focus();
  }
  const active = !!filter;
  const inputType = kind === "date" ? "date" : "number";
  return (
    <span className={styles.filterWrap}>
      <button
        ref={anchor}
        type="button"
        className={styles.filterButton}
        aria-label={`Filter ${col.label}`}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        data-active={active}
        onClick={() => setOpen((o) => !o)}
      >
        <Filter size={12} strokeWidth={active ? 2.6 : 1.8} aria-hidden="true" />
      </button>
      <Popover open={open} onClose={close} anchorRef={anchor} label={`Filter ${col.label}`} id={id} className={styles.filterMenu}>
        {col.sort ? (
          <div className={styles.filterSort}>
            <Button size="small" onClick={() => { onSortTo(col.sort!); close(); }} aria-pressed={sort === col.sort}>
              Sort {sortDirection(col.sort)}
            </Button>
            <Button size="small" onClick={() => { onSortTo(`-${col.sort}`); close(); }} aria-pressed={sort === `-${col.sort}`}>
              Sort {sortDirection(`-${col.sort}`)}
            </Button>
          </div>
        ) : null}
        {kind === "values" ? (
          <ValuesList col={col} field={field} params={params} picked={picked} setPicked={setPicked} />
        ) : (
          <div className={styles.filterRange}>
            <label>
              <span>{kind === "date" ? "From" : "Min"}</span>
              <TextInput type={inputType} value={min} onValueChange={setMin} step={kind === "range" ? "any" : undefined} />
            </label>
            <label>
              <span>{kind === "date" ? "To" : "Max"}</span>
              <TextInput type={inputType} value={max} onValueChange={setMax} step={kind === "range" ? "any" : undefined} />
            </label>
          </div>
        )}
        <div className={styles.filterActions}>
          <Button size="small" onClick={clear} disabled={!active}>
            Clear filter
          </Button>
          <Button size="small" variant="primary" onClick={apply}>
            Apply
          </Button>
        </div>
      </Popover>
    </span>
  );
}

interface ValuesListProps {
  col: Column;
  field: FilterField;
  params: FilterParams;
  picked: Set<string>;
  setPicked: (next: Set<string>) => void;
}

/** The searchable checklist; mounted only while the menu is open, so the facets are fetched on open. */
function ValuesList({ col, field, params, picked, setPicked }: ValuesListProps) {
  const [search, setSearch] = useState("");
  const facets = useJobFacets(field, params, true);
  const options = useMemo(() => {
    const seen = new Map<string, number>();
    for (const v of facets.data?.values ?? []) if (v.value !== null && v.value !== "") seen.set(String(v.value), v.count);
    for (const v of picked) if (!seen.has(v)) seen.set(v, 0);
    const needle = search.trim().toLowerCase();
    return [...seen].filter(([v]) => !needle || facetLabel(field, v).toLowerCase().includes(needle));
  }, [facets.data, picked, search, field]);
  function toggle(v: string) {
    const next = new Set(picked);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    setPicked(next);
  }
  return (
    <>
      <TextInput
        type="search"
        aria-label={`Search ${col.label} values`}
        placeholder="Search values"
        value={search}
        onValueChange={setSearch}
      />
      <div className={styles.filterLinks}>
        <button type="button" className={styles.linkButton} onClick={() => setPicked(new Set(options.map(([v]) => v)))}>
          Select all
        </button>
        <button type="button" className={styles.linkButton} onClick={() => setPicked(new Set())}>
          Clear
        </button>
      </div>
      <ul className={styles.filterList} aria-label={`${col.label} values`} aria-busy={facets.isPending || undefined}>
        {options.map(([v, n]) => (
          <li key={v}>
            <label className={styles.filterOption}>
              <input type="checkbox" checked={picked.has(v)} onChange={() => toggle(v)} />
              <span className={styles.filterOptionText}>{facetLabel(field, v)}</span>{" "}
              <span className={`tabular ${styles.filterCount}`}>({n})</span>
            </label>
          </li>
        ))}
        {!facets.isPending && options.length === 0 ? <li className={styles.filterEmpty}>No values</li> : null}
      </ul>
    </>
  );
}
