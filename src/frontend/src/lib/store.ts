import { create } from "zustand";
import { safeSessionStorage } from "./storage";
import { createJSONStorage, persist } from "zustand/middleware";
import {
  defaults,
  backgroundJobSchema,
  type BackgroundJob,
  originSchema,
  preferencesDraftSchema,
  prefillSnapshotSchema,
  accountDefaults,
  type PrefillSnapshot,
  type Origin,
  type Preferences,
} from "./schemas";
interface Draft {
  ownerId: string | null;
  hasDraft: boolean;
  origin: Origin | null;
  preferences: Preferences;
  prefill: PrefillSnapshot | null;
  initialize: (
    preferences: Preferences,
    source: PrefillSnapshot["source"],
    revision: number | null,
  ) => void;
  startNewMeal: () => void;
  runId: string | null;
  job: BackgroundJob | null;
  setJob: (job: BackgroundJob | null) => void;
  enqueue: (
    kind: BackgroundJob["kind"],
    path: string,
    body: Record<string, unknown>,
    runId?: string | null,
  ) => void;
  setOwnerId: (ownerId: string) => void;
  setOrigin: (origin: Origin | null) => void;
  setPreferences: (preferences: Preferences) => void;
  setRunId: (runId: string | null) => void;
  reset: () => void;
}

function recoverDraft(value: unknown) {
  const stored =
    value && typeof value === "object"
      ? (value as Record<string, unknown>)
      : {};
  const preferences = preferencesDraftSchema.safeParse(stored.preferences);
  const origin = originSchema.safeParse(stored.origin);
  const prefill = prefillSnapshotSchema.safeParse(stored.prefill);
  const job = backgroundJobSchema.safeParse(stored.job);
  return {
    ownerId:
      typeof stored.ownerId === "string" && stored.ownerId
        ? stored.ownerId
        : null,
    hasDraft:
      stored.hasDraft === true && preferences.success && prefill.success,
    prefill: prefill.success ? prefill.data : null,
    job: job.success ? job.data : null,
    preferences: preferences.success ? preferences.data : defaults,
    origin: origin.success ? origin.data : null,
    runId: typeof stored.runId === "string" ? stored.runId : null,
  };
}
export const useDraft = create<Draft>()(
  persist(
    (set) => ({
      ownerId: null,
      hasDraft: false,
      origin: null,
      preferences: defaults,
      prefill: null,
      initialize: (preferences, source, revision) =>
        set({
          preferences: preferencesDraftSchema.parse(preferences),
          hasDraft: true,
          runId: null,
          job: null,
          prefill: {
            values: structuredClone(accountDefaults(preferences)),
            source,
            revision,
          },
        }),
      startNewMeal: () =>
        set({
          hasDraft: false,
          preferences: defaults,
          prefill: null,
          runId: null,
          job: null,
        }),
      runId: null,
      job: null,
      setJob: (job) => set({ job }),
      enqueue: (kind, path, body, runId = null) =>
        set((state) => ({
          job: backgroundJobSchema.parse({
            key:
              state.job &&
              state.job.status !== "saved" &&
              state.job.kind === kind &&
              state.job.path === path &&
              state.job.runId === runId &&
              JSON.stringify(state.job.body) === JSON.stringify(body)
                ? state.job.key
                : crypto.randomUUID(),
            kind,
            path,
            body,
            runId,
            status: "submitting",
            error: null,
          }),
        })),
      setOwnerId: (ownerId) => set({ ownerId }),
      setOrigin: (origin) => set({ origin }),
      setPreferences: (preferences) =>
        set({
          preferences: preferencesDraftSchema.parse(preferences),
          hasDraft: true,
        }),
      setRunId: (runId) =>
        set((state) => ({ runId, job: runId === null ? null : state.job })),
      reset: () =>
        set({
          ownerId: null,
          hasDraft: false,
          origin: null,
          preferences: defaults,
          prefill: null,
          runId: null,
          job: null,
        }),
    }),
    {
      name: "food-draft-v1",
      version: 8,
      storage: createJSONStorage(() => safeSessionStorage),
      partialize: ({
        ownerId,
        hasDraft,
        preferences,
        prefill,
        origin,
        runId,
        job,
      }) => ({
        ownerId,
        hasDraft,
        preferences,
        prefill,
        origin,
        runId,
        job,
      }),
      migrate: () => recoverDraft(null),
      merge: (stored, current) => ({ ...current, ...recoverDraft(stored) }),
    },
  ),
);
