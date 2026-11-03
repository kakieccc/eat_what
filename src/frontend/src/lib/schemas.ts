import { z } from "zod";
import { navigationHref } from "./utils";
export type Point = { latitude: number; longitude: number };
export const cuisines = [
  "中餐",
  "面馆",
  "火锅",
  "烧烤",
  "快餐",
  "轻食",
  "日韩料理",
  "东南亚料理",
  "西餐",
  "咖啡甜品",
  "小吃",
  "其他餐饮",
];
export const excludedCuisineOptions = [
  "川菜", "湘菜", "粤菜", "江浙菜", "鲁菜", "徽菜", "闽菜", "东北菜",
  "西北菜", "日韩料理", "东南亚料理", "西餐",
];
export const originSchema = z.object({
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  address: z.string().max(200),
});
export type Origin = z.infer<typeof originSchema>;
export const radiusValues = [500, 1000, 2000, 5000] as const;
export type SearchRadius = (typeof radiusValues)[number];
export function isSearchRadius(value: unknown): value is SearchRadius {
  return radiusValues.some((radius) => radius === value);
}
const money = z
  .string()
  .refine(
    (v) =>
      v === "" ||
      (/^\d+(?:\.\d{1,2})?$/.test(v) && Number(v) <= 10000),
    "请输入 0–10000 的金额，最多两位小数",
  )
  .nullable();
export const allowedFoodLimit = 5;
const foodNames = z.array(z.string().trim().min(1).max(30));
export const budgetSchema = z
  .object({ min: money, max: money })
  .refine(
    (b) =>
      b.min === null ||
      b.max === null ||
      b.min === "" ||
      b.max === "" ||
      Number(b.min) <= Number(b.max),
    "预算下限不能高于上限",
  );
export const preferencesSchema = z
  .object({
    budgetPerPerson: budgetSchema,
    radiusMeters: z.custom<SearchRadius>(
      isSearchRadius,
      "请选择 500 米、1 km、2 km 或 5 km 的搜索半径",
    ),
    allowedFoods: foodNames.max(allowedFoodLimit, `限定食物类型最多 ${allowedFoodLimit} 项`),
    excludedFoods: foodNames.max(12, "最多排除 12 种菜系"),
    mealPeriod: z.enum(["breakfast", "lunch", "dinner", "lateNight"]),
    partySize: z.number().int().min(1).max(20),
    requestText: z.string().max(1000),
  })
  .refine(
    (p) =>
      !p.allowedFoods.some((c) =>
        p.excludedFoods.includes(c),
      ),
    { message: "限定的食物不能同时被排除", path: ["excludedFoods"] },
  );
export type Preferences = z.infer<typeof preferencesSchema>;
export const preferencesDraftSchema = z.object({
  ...preferencesSchema.shape,
  budgetPerPerson: z.object({ min: z.string().nullable(), max: z.string().nullable() }),
  allowedFoods: z.array(z.string()),
  excludedFoods: z.array(z.string()),
  // A cleared number input becomes NaN, which JSON stores as null.
  partySize: z.number().or(z.nan()).nullable().transform((value) => value ?? Number.NaN),
  requestText: z.string(),
});
const mealPreferencesSchema = z.object(preferencesSchema.shape).pick({
  budgetPerPerson: true,
  radiusMeters: true,
  allowedFoods: true,
  excludedFoods: true,
});
export const accountDefaultsSchema = mealPreferencesSchema.extend({
  requestText: z.string().max(1000),
}).strict();
export type AccountDefaults = z.infer<typeof accountDefaultsSchema>;
export const preferenceOverridesSchema = accountDefaultsSchema.partial();
export type PreferenceOverrides = z.infer<typeof preferenceOverridesSchema>;
export const learnableFields = ["budgetPerPerson", "radiusMeters", "requestText"] as const;
export type LearnableField = (typeof learnableFields)[number];
export const accountPreferencesSchema = z.object({
  defaults: accountDefaultsSchema,
  sources: z.record(z.string(), z.enum(["manual", "learned", "builtin"])),
  overrides: preferenceOverridesSchema,
  revision: z.number().int().nonnegative(),
  learning: z.object({
    enabled: z.boolean(),
    mealCount: z.number().int().nonnegative(),
    status: z.enum(["idle", "queued", "running", "failed"]),
    lastSuccessAt: z.string().nullable(),
    nextLearningAt: z.number().int(),
  }),
});
export type AccountPreferences = z.infer<typeof accountPreferencesSchema>;
export const prefillSnapshotSchema = z.object({
  values: accountDefaultsSchema,
  source: z.enum(["defaults", "history"]),
  revision: z.number().int().nonnegative().nullable(),
});
export type PrefillSnapshot = z.infer<typeof prefillSnapshotSchema>;
export function accountDefaults(p: Preferences): AccountDefaults {
  return {
    budgetPerPerson: p.budgetPerPerson, radiusMeters: p.radiusMeters,
    allowedFoods: p.allowedFoods, excludedFoods: p.excludedFoods, requestText: p.requestText,
  };
}
export function sameDefault(a: unknown, b: unknown): boolean {
  if (a && b && typeof a === "object" && typeof b === "object" && "min" in a && "min" in b && "max" in a && "max" in b) {
    const money = (value: unknown) => value === "" || value === null ? null : Number(value);
    return money(a.min) === money(b.min) && money(a.max) === money(b.max);
  }
  return JSON.stringify(a) === JSON.stringify(b);
}
export function editedOverrides(
  baseline: AccountPreferences, p: Preferences, automatic: LearnableField[],
): PreferenceOverrides {
  const values = accountDefaults(p);
  const overrides: PreferenceOverrides = { ...baseline.overrides };
  // Saving unrelated fields must not turn unchanged learned defaults into manual overrides.
  for (const key of Object.keys(values) as (keyof AccountDefaults)[]) {
    if (!sameDefault(values[key], baseline.defaults[key])) {
      Object.assign(overrides, { [key]: values[key] });
    }
  }
  for (const key of automatic) delete overrides[key];
  return overrides;
}
export const decisionRequestSchema = z.object({
  origin: originSchema,
  preferences: mealPreferencesSchema.strict(),
  mealPeriod: z.enum(["breakfast", "lunch", "dinner", "lateNight"]),
  partySize: z.number().int().min(1).max(20),
  requestText: z.string().max(1000),
});
export type DecisionRequest = z.infer<typeof decisionRequestSchema>;
export function toDecisionRequest(
  p: Preferences,
  origin: Origin,
): DecisionRequest {
  const { mealPeriod, partySize, requestText, ...preferences } = p;
  return {
    origin,
    preferences,
    mealPeriod,
    partySize,
    requestText,
  };
}
export function fromDecisionRequest(r: DecisionRequest): Preferences {
  return {
    ...r.preferences,
    mealPeriod: r.mealPeriod,
    partySize: r.partySize,
    requestText: r.requestText,
  };
}
export const defaults: Preferences = {
  budgetPerPerson: { min: "20", max: "60" },
  radiusMeters: 2000,
  allowedFoods: [],
  excludedFoods: [],
  mealPeriod: "lunch",
  partySize: 1,
  requestText: "",
};
export const placeSchema = z.object({
  id: z.string(),
  externalId: z.string(),
  source: z.literal("amap"),
  name: z.string(),
  categoryCode: z.string(),
  categoryName: z.string(),
  cuisineTypes: z.array(z.string()),
  address: z.string(),
  location: originSchema.omit({ address: true }),
  straightLineDistanceMeters: z.number().nonnegative(),
  rating: z.number().nullable(),
  averageCost: z.string().nullable(),
  openingHoursText: z.string().nullable(),
  phone: z.string().nullable(),
  photos: z.array(z.string()),
  dataUpdatedAt: z.string(),
  score: z.number(),
  scoreBreakdown: z.record(z.string(), z.number()),
  reason: z.string(),
  warnings: z.array(z.string()),
  navigationUrl: z.string().nullable().transform(navigationHref),
  candidateId: z.string().nullable(),
  rank: z.number().int(),
});
export type Place = z.infer<typeof placeSchema>;
export const choiceSchema = z.object({
  id: z.string(),
  candidateId: z.string(),
  decisionRunId: z.string(),
  selectedAt: z.string(),
});
export const runSchema = z.object({
  decisionRunId: z.string(),
  discoverySessionId: z.string(),
  status: z.enum(["pending", "running", "completed", "failed"]),
  places: z.array(placeSchema),
  request: decisionRequestSchema,
  originalRequest: decisionRequestSchema,
  filterSummary: z.record(z.string(), z.number()),
  suggestions: z.array(z.string()),
  warnings: z.array(z.string()),
  errorCode: z.string().nullable(),
  choice: choiceSchema.nullable(),
});
export type Run = z.infer<typeof runSchema>;
export const historySchema = z.object({
  items: z.array(z.object({
    id: z.string(),
    createdAt: z.string(),
    request: decisionRequestSchema,
    choice: z.object({
      id: z.string(),
      decisionRunId: z.string(),
      place: placeSchema,
    }),
  })),
  nextCursor: z.string().nullable(),
});
export const userSchema = z.object({
  id: z.string(),
  username: z.string(),
  displayName: z.string(),
  createdAt: z.string(),
});
export type User = z.infer<typeof userSchema>;
export const authPayloadSchema = z.object({
  user: userSchema,
  csrfToken: z.string().min(1),
});
export type AuthPayload = z.infer<typeof authPayloadSchema>;
export const eventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("runStarted"),
    requestId: z.string(),
    decisionRunId: z.string(),
  }),
  z.object({
    type: z.literal("nodeStarted"),
    node: z.string(),
    label: z.string(),
  }),
  z.object({
    type: z.literal("nodeCompleted"),
    node: z.string(),
    durationMs: z.number(),
    outputCount: z.number().nullable(),
  }),
  z.object({ type: z.literal("result"), data: runSchema }),
  z.object({
    type: z.literal("runFailed"),
    error: z.object({
      code: z.string(),
      message: z.string(),
      retryable: z.boolean(),
    }),
  }),
  z.object({ type: z.literal("heartbeat"), timestamp: z.string() }),
]);
export type DecisionEvent = z.infer<typeof eventSchema>;


export const backgroundJobSchema = z.object({
  key: z.string(),
  kind: z.enum(["recommendation", "choice"]),
  path: z.string().regex(/^\/(?:decision-runs(?:\/[^/]+\/(?:refinements|retry))?|place-choices)$/),
  body: z.record(z.string(), z.unknown()),
  runId: z.string().nullable(),
  status: z.enum(["submitting", "failed", "rejected", "saved"]),
  error: z.string().nullable(),
});
export type BackgroundJob = z.infer<typeof backgroundJobSchema>;
export const choiceResultSchema = z.object({ id: z.string(), candidateId: z.string() });
