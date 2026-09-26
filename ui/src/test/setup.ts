import "@testing-library/jest-dom/vitest";

// Tests read dates and numbers in one locale and time zone whatever the machine uses (LC_ALL=fr_FR.UTF-8 too):
// Intl formatters with no explicit locale get en-US, and the process runs in UTC.
process.env.TZ = "UTC";
const PINNED = "en-US";
function pin<T extends abstract new (...args: never[]) => unknown>(Ctor: T): T {
  return new Proxy(Ctor, {
    construct(target, args: unknown[]) {
      const [locale, ...rest] = args;
      return Reflect.construct(target, [locale ?? PINNED, ...rest]);
    },
  });
}
for (const name of ["DateTimeFormat", "NumberFormat", "RelativeTimeFormat"] as const) {
  Object.defineProperty(Intl, name, { value: pin(Intl[name]), configurable: true, writable: true });
}
