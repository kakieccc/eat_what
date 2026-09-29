import { z } from "zod";
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
export const originSchema = z.object({
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  address: z.string(),
});
export type Origin = z.infer<typeof originSchema>;
const money = z
  .string()
  .refine(
    (v) =>
      v === "" ||
      (Number.isFinite(Number(v)) && Number(v) >= 0 && Number(v) <= 10000),
    "请输入 0–10000 的金额",
  )
  .nullable();
export const preferencesSchema = z
  .object({
    budgetPerPerson: z
      .object({ min: money, max: money })
      .refine(
        (b) =>
          b.min === null ||
          b.max === null ||
          b.min === "" ||
          b.max === "" ||
          Number(b.min) <= Number(b.max),
        "预算下限不能高于上限",
      ),
    maxWalkingMinutes: z.number().int().min(1).max(60),
    radiusMeters: z.number().int().min(100).max(50000),
    preferredCuisines: z.array(z.string()),
    excludedCuisines: z.array(z.string()),
    desiredTags: z.array(z.string()).max(5),
    mealPeriod: z.enum(["breakfast", "lunch", "dinner", "lateNight"]),
    partySize: z.number().int().min(1).max(20),
    openNowPreferred: z.boolean(),
    requestText: z.string().max(300),
  })
  .refine(
    (p) => !p.preferredCuisines.some((c) => p.excludedCuisines.includes(c)),
    "喜欢和排除的菜系不能重叠",
  );
export type Preferences = z.infer<typeof preferencesSchema>;
export const defaults: Preferences = {
  budgetPerPerson: { min: "20", max: "60" },
  maxWalkingMinutes: 15,
  radiusMeters: 2000,
  preferredCuisines: [],
  excludedCuisines: [],
  desiredTags: [],
  mealPeriod: "lunch",
  partySize: 1,
  openNowPreferred: true,
  requestText: "",
};
const routeSchema = z.object({
  mode: z.literal("walking"),
  source: z.literal("amap"),
  distanceMeters: z.number().nonnegative(),
  durationSeconds: z.number().nonnegative(),
  polyline: z.array(originSchema.omit({ address: true })),
});
export type Route = z.infer<typeof routeSchema>;
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
  averageCost: z.union([z.number(), z.string()]).nullable(),
  businessStatus: z.enum(["open", "closed", "unknown"]),
  openingHoursText: z.string().nullable(),
  phone: z.string().nullable(),
  photos: z.array(z.string()),
  route: routeSchema.nullable(),
  dataUpdatedAt: z.string(),
  score: z.number(),
  scoreBreakdown: z.record(z.string(), z.number()),
  reason: z.string(),
  warnings: z.array(z.string()),
  navigationUrl: z.string().nullable(),
  candidateId: z.string().nullable(),
  rank: z.number().int(),
});
export type Place = z.infer<typeof placeSchema>;
const confirmationChangeSchema = z.object({
  before: z.unknown(),
  after: z.unknown(),
});
export const runSchema = z
  .object({
    decisionRunId: z.string(),
    discoverySessionId: z.string(),
    status: z.enum([
      "pending",
      "running",
      "awaitingConfirmation",
      "completed",
      "failed",
    ]),
    places: z.array(placeSchema),
    request: preferencesSchema.extend({ origin: originSchema }),
    confirmation: z.record(z.string(), confirmationChangeSchema).nullable(),
    filterSummary: z.record(z.string(), z.number()),
    suggestions: z.array(z.string()),
    errorCode: z.string().nullable(),
    chosenCandidateIds: z.array(z.string()),
  })
  .passthrough();
export type Run = z.infer<typeof runSchema>;
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
    outputCount: z.number().nullable().optional(),
  }),
  z.object({ type: z.literal("result"), data: runSchema }),
  z.object({ type: z.literal("confirmationRequired"), data: runSchema }),
  z.object({
    type: z.literal("runFailed"),
    error: z.object({
      code: z.string(),
      message: z.string(),
      retryable: z.boolean().optional(),
    }),
  }),
  z.object({ type: z.literal("heartbeat"), timestamp: z.string() }),
]);
export type DecisionEvent = z.infer<typeof eventSchema>;
