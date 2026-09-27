import { describe, expect, it } from "vitest";
import { DEFAULT_SORT, readView, sortCaption, toggleSort, writeView } from "./urlState";

describe("Jobs URL state", () => {
  it("reads defaults from an empty query string", () => {
    expect(readView(new URLSearchParams())).toEqual({
      tab: "active",
      q: "",
      location: "",
      sort: DEFAULT_SORT,
      hidden: [],
      selected: [],
    });
  });

  it("reads tab, q, sort, hidden columns and selection; ignores junk", () => {
    const v = readView(new URLSearchParams("tab=tier_a&q=data&loc=remote&sort=company&cols=ats,qa,bogus&sel=a1,b2"));
    expect(v).toEqual({
      tab: "tier_a",
      q: "data",
      location: "remote",
      sort: "company",
      hidden: ["ats", "qa"],
      selected: ["a1", "b2"],
    });
    expect(readView(new URLSearchParams("sort=-location")).sort).toBe("-location");
    expect(readView(new URLSearchParams("tab=nope&sort=drop_table")).tab).toBe("active");
    expect(readView(new URLSearchParams("sort=drop_table")).sort).toBe(DEFAULT_SORT);
  });

  it("writes only non-default values, keeping unrelated params", () => {
    const p = writeView(new URLSearchParams("x=1&tab=review"), { tab: "active", q: "globex", sort: "-fit" });
    expect(p.toString()).toBe("x=1&q=globex");
    expect(writeView(new URLSearchParams(), { location: " Remote " }).toString()).toBe("loc=Remote");
    expect(writeView(new URLSearchParams(), { hidden: ["ats"], selected: ["a1", "b2"] }).toString()).toBe(
      "cols=ats&sel=a1%2Cb2",
    );
  });

  it("clicking a header sorts by it in its natural direction, clicking again flips it", () => {
    expect(toggleSort("-fit", "fit")).toBe("fit");
    expect(toggleSort("fit", "fit")).toBe("-fit");
    expect(toggleSort("-fit", "company")).toBe("company");
    expect(toggleSort("-fit", "found_at")).toBe("-found_at");
  });

  it("describes the sort in words for the table caption", () => {
    expect(sortCaption("-fit")).toBe("sorted by fit, highest first");
    expect(sortCaption("company")).toBe("sorted by company, A to Z");
    expect(sortCaption("-location")).toBe("sorted by location, Z to A");
    expect(sortCaption("-applied_at")).toBe("sorted by applied date, newest first");
  });
});
