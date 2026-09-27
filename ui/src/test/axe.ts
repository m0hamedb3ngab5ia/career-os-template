import axe from "axe-core";

// jsdom has no layout or computed colours, so colour-contrast is checked in the browser pass, not here.
export async function axeViolations(el: Element): Promise<string[]> {
  const res = await axe.run(el, { rules: { "color-contrast": { enabled: false } } });
  return res.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`);
}
