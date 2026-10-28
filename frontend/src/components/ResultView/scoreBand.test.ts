import { describe, expect, it } from "vitest";
import { getScoreBand } from "./scoreBand";

describe("getScoreBand", () => {
  it.each([
    [100, "good"],
    [80, "good"],
    [79, "fair"],
    [50, "fair"],
    [49, "needs-work"],
    [0, "needs-work"],
  ])("score %i is %s", (score, band) => {
    expect(getScoreBand(score)).toBe(band);
  });
});