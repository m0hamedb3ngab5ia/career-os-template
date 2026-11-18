import { describe, expect, it } from "vitest";
import { filterSections, isCommand, splitCode } from "./filter";

const sections = [
  { title: "Start here", rows: [], notes: ["1. Run doctor."] },
  { title: "1. Set up", rows: [{ feature: "Init", what: "Copies the example.", how: "`careeros init`", req: "" }] },
  { title: "2. Find jobs", rows: [
    { feature: "Scout", what: "Pulls job boards.", how: "`careeros scout --sync`", req: "REQ-001" },
    { feature: "Boards", what: "Finds a board.", how: "`careeros company find-board`", req: "" },
  ] },
];

describe("filterSections", () => {
  it("returns everything for an empty query", () => expect(filterSections(sections, "  ")).toEqual(sections));
  it("drops prose-only sections while searching", () =>
    expect(filterSections(sections, "doctor").map((s) => s.title)).toEqual([]));
  it("matches any column, case-insensitively, and drops empty sections", () => {
    const r = filterSections(sections, "SYNC");
    expect(r.map((s) => s.title)).toEqual(["2. Find jobs"]);
    expect(r[0]!.rows.map((x) => x.feature)).toEqual(["Scout"]);
  });
  it("needs every word", () => {
    expect(filterSections(sections, "board company")[0]!.rows.map((x) => x.feature)).toEqual(["Boards"]);
    expect(filterSections(sections, "scout zzz")).toEqual([]);
  });
});

describe("splitCode", () => {
  it("marks backticked parts as code", () =>
    expect(splitCode("`a b`; or say hi")).toEqual([{ code: true, text: "a b" }, { code: false, text: "; or say hi" }]));
});

describe("isCommand", () => {
  it("copies commands and skills, not paths", () => {
    expect(isCommand("careeros resume list")).toBe(true);
    expect(isCommand("/learn-voice")).toBe(true);
    expect(isCommand("profile/voice/samples/")).toBe(false);
    expect(isCommand("config/companies.yaml")).toBe(false);
  });
});
