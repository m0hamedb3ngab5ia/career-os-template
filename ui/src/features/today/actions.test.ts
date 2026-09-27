import { describe, expect, it } from "vitest";
import { filterActions, linkInfo, parseFilter, parseSort, sortActions } from "./actions";
import { actionItem } from "./testing";
import type { ActionItem } from "./types";

const now = new Date("2026-09-25T10:00:00Z");

// Fictional companies only.
const items: ActionItem[] = [
  actionItem({ id: "1", company: "Globex", what: "a", priority: "L", needs: "anytime", created: "2026-09-20", due: null }),
  actionItem({ id: "2", company: "Acme Robotics", what: "b", priority: "H", needs: "laptop", created: "2026-09-24",
    due: "2026-10-03T12:00:00Z" }),
  actionItem({ id: "3", company: "Initech", what: "c", priority: "M", needs: "phone", created: "2026-09-22",
    due: "2026-09-24T09:00:00Z" }),
  actionItem({ id: "4", company: "Hooli", what: "d", priority: "H", needs: "phone", created: "2026-09-23",
    due: "2026-09-26T15:00:00Z" }),
];
const ids = (xs: ActionItem[]) => xs.map((x) => x.id);

describe("sortActions", () => {
  it("priority: H→L, then soonest due, undated last", () => {
    expect(ids(sortActions(items, "priority"))).toEqual(["4", "2", "3", "1"]);
  });
  it("due: soonest first, undated last, ties by priority", () => {
    expect(ids(sortActions(items, "due"))).toEqual(["3", "4", "2", "1"]);
  });
  it("A–Z by company", () => {
    expect(ids(sortActions(items, "az"))).toEqual(["2", "1", "4", "3"]);
  });
  it("A–Z puts an item with no company last instead of crashing", () => {
    const noCompany = { ...items[0]!, id: "5", company: undefined as unknown as string };
    const zz = { ...items[0]!, id: "6", company: "Zzyzx" };
    expect(ids(sortActions([noCompany, ...items], "az"))).toEqual(["2", "1", "4", "3", "5"]);
    expect(ids(sortActions([...items, noCompany, zz], "az"))).toEqual(["2", "1", "4", "3", "6", "5"]);
    expect(ids(sortActions([zz, noCompany], "az"))).toEqual(["6", "5"]);
    expect(ids(sortActions([noCompany, zz], "az"))).toEqual(["6", "5"]);
  });
  it("newest by created", () => {
    expect(ids(sortActions(items, "newest"))).toEqual(["2", "4", "3", "1"]);
  });
  it("does not mutate its input", () => {
    const copy = [...items];
    sortActions(items, "az");
    expect(items).toEqual(copy);
  });
});

describe("filterActions", () => {
  it.each([
    ["all", ["1", "2", "3", "4"]],
    ["overdue", ["3"]],
    ["soon", ["3", "4"]],
    ["high", ["2", "4"]],
    ["phone", ["1", "3", "4"]],
    ["laptop", ["2"]],
    ["nodate", ["1"]],
  ] as const)("%s", (f, want) => {
    expect(ids(filterActions(items, f, now))).toEqual(want);
  });
});

describe("URL values", () => {
  it("fall back to the defaults for missing or unknown values", () => {
    expect(parseSort(null)).toBe("priority");
    expect(parseSort("due")).toBe("due");
    expect(parseSort("bogus")).toBe("priority");
    expect(parseFilter(null)).toBe("all");
    expect(parseFilter("high")).toBe("high");
    expect(parseFilter("nope")).toBe("all");
  });
});

describe("linkInfo", () => {
  it("labels web links by host", () => {
    expect(linkInfo("https://www.example.com/jobs/123")).toEqual({ kind: "web", href: "https://www.example.com/jobs/123", label: "Open example.com" });
    expect(linkInfo("http://jobs.example.org")).toEqual({ kind: "web", href: "http://jobs.example.org", label: "Open jobs.example.org" });
  });
  it("shows anything that isn't http(s) as text, never as a broken anchor", () => {
    expect(linkInfo("profile/master.yaml")).toEqual({ kind: "text", text: "profile/master.yaml" });
    expect(linkInfo("javascript:alert(1)")).toEqual({ kind: "text", text: "javascript:alert(1)" });
  });
  it("has nothing for an empty link", () => {
    expect(linkInfo("")).toBeNull();
    expect(linkInfo(null)).toBeNull();
  });
});
