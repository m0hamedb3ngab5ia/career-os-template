import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ListInput } from "./fields";

describe("ListInput", () => {
  it("renders items that don't round-trip through comma splitting without looping", () => {
    render(<ListInput label="Skills" value={["Python, SQL", "", "Go"]} locked={false} onChange={() => {}} />);
    expect(screen.getByDisplayValue("Python, SQL, , Go")).toBeTruthy();
  });
});

describe("single-line Field", () => {
  it("is a wrapping textarea that refuses newlines", async () => {
    const { Field } = await import("./fields");
    const { fireEvent } = await import("@testing-library/react");
    const seen: string[] = [];
    render(<Field label="Title" value="a" locked={false} onChange={(v) => seen.push(v)} />);
    const el = screen.getByLabelText("Title") as HTMLTextAreaElement;
    expect(el.tagName).toBe("TEXTAREA");
    expect(fireEvent.keyDown(el, { key: "Enter" })).toBe(false);  // default prevented
    fireEvent.change(el, { target: { value: "a\nb" } });
    expect(seen).toEqual(["a b"]);
  });
});
