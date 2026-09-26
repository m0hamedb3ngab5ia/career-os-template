import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

configure({ asyncUtilTimeout: 4000 });

// Pin the default locale to en-US so number, date and relative-time assertions pass whatever the machine's
// locale is (e.g. LC_ALL=fr_FR.UTF-8). Code that passes an explicit locale is unaffected.
const LOCALE = "en-US";
for (const name of ["NumberFormat", "DateTimeFormat", "RelativeTimeFormat", "PluralRules", "ListFormat"] as const) {
  const Orig = Intl[name] as unknown as new (locales?: string | string[], options?: object) => object;
  if (!Orig) continue;
  const Pinned = function (this: unknown, locales?: string | string[], options?: object) {
    return new Orig(locales ?? LOCALE, options);
  } as unknown as typeof Orig;
  Object.assign(Pinned, Orig);
  Pinned.prototype = Orig.prototype;
  Object.defineProperty(Intl, name, { value: Pinned, configurable: true, writable: true });
}
const toLocale = Number.prototype.toLocaleString;
Number.prototype.toLocaleString = function (locales?: string | string[], options?: Intl.NumberFormatOptions) {
  return toLocale.call(this, locales ?? LOCALE, options);
};
