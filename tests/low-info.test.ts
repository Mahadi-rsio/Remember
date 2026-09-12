import { describe, expect, it } from "bun:test";
import { isLowInfoMessage } from "../src/memory/low-info";

describe("Low Information Detection", () => {
  it("detects basic affirmations and acknowledgements as low info", () => {
    expect(isLowInfoMessage("ok")).toBe(true);
    expect(isLowInfoMessage("okay")).toBe(true);
    expect(isLowInfoMessage("sounds good to me")).toBe(true);
    expect(isLowInfoMessage("thanks a lot")).toBe(true);
    expect(isLowInfoMessage("cool")).toBe(true);
    expect(isLowInfoMessage("lgtm")).toBe(true);
    expect(isLowInfoMessage("yes")).toBe(true);
  });

  it("does not classify substantive messages as low info", () => {
    expect(isLowInfoMessage("We are building Cloudisy with PostgreSQL")).toBe(false);
    expect(isLowInfoMessage("Deploy the new version to AWS Lambda")).toBe(false);
    expect(isLowInfoMessage("I prefer Tailwind over Bootstrap")).toBe(false);
  });
});
