import { it, expect } from "vitest";
import { defaults, preferencesSchema, runSchema } from "./schemas";
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

it("accepts direct confirmation changes and rejects a missing contract field", () => {
  const run = {
    decisionRunId: "run-1",
    discoverySessionId: "session-1",
    status: "awaitingConfirmation",
    request: {
      ...defaults,
      origin: { latitude: 31.2, longitude: 121.5, address: "上海" },
    },
    places: [],
    confirmation: { maxWalkingMinutes: { before: 15, after: 25 } },
    filterSummary: {},
    suggestions: [],
    errorCode: null,
    chosenCandidateIds: [],
  };
  expect(runSchema.parse(run).confirmation?.maxWalkingMinutes.after).toBe(25);
  expect(runSchema.safeParse({ ...run, confirmation: { changes: run.confirmation } }).success).toBe(false);
  expect(runSchema.safeParse({ ...run, places: undefined }).success).toBe(false);
});
