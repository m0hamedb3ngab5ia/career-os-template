/** The part of `a` a suggestion replaces and what replaces it: whole words, the shared start and end cut to "…"
 * (the field above already shows them), so the inline diff strikes only what changes. */
export function changedSpan(a: string, b: string): { before: string; del: string; ins: string; after: string } {
  const x = a.split(/\s+/).filter(Boolean), y = b.split(/\s+/).filter(Boolean);
  let i = 0;
  while (i < x.length && i < y.length && x[i] === y[i]) i++;
  let j = 0;
  while (j < x.length - i && j < y.length - i && x[x.length - 1 - j] === y[y.length - 1 - j]) j++;
  return { before: i ? "…" : "", del: x.slice(i, x.length - j).join(" "), ins: y.slice(i, y.length - j).join(" "), after: j ? "…" : "" };
}
