/** Split a suggestion into the text it keeps and the words it changes (whole words; whitespace kept as is), so the
 * field can strike only the changed words in place, Docs-style. before + del + after = a; before + ins + after = b. */
export function changedSpan(a: string, b: string): { before: string; del: string; ins: string; after: string } {
  const x = a.split(/(\s+)/), y = b.split(/(\s+)/);
  let i = 0;
  while (i < x.length && i < y.length && x[i] === y[i]) i++;
  let j = 0;
  while (j < x.length - i && j < y.length - i && x[x.length - 1 - j] === y[y.length - 1 - j]) j++;
  return { before: x.slice(0, i).join(""), del: x.slice(i, x.length - j).join(""), ins: y.slice(i, y.length - j).join(""),
    after: x.slice(x.length - j).join("") };
}
