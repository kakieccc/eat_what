import { it, expect } from "vitest";
import { defaults, preferencesSchema } from "./schemas";
it("validates budget and mutually exclusive preferences", () => {
  expect(preferencesSchema.safeParse(defaults).success).toBe(true);
  expect(
    preferencesSchema.safeParse({
      ...defaults,
      budgetPerPerson: { min: "60", max: "20" },
    }).success,
  ).toBe(false);
  expect(
    preferencesSchema.safeParse({
      ...defaults,
      preferredCuisines: ["火锅"],
      excludedCuisines: ["火锅"],
    }).success,
  ).toBe(false);
});
