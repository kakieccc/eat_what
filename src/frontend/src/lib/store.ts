import { create } from "zustand";
import { safeSessionStorage } from "./storage";
import { createJSONStorage, persist } from "zustand/middleware";
import {
  defaults,
  originSchema,
  preferencesDraftSchema,
  type Origin,
  type Preferences,
} from "./schemas";
interface Draft {
  ownerId: string | null;
  hasDraft: boolean;
  origin: Origin | null;
  preferences: Preferences;
  runId: string | null;
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
  return {
    ownerId: typeof stored.ownerId === "string" && stored.ownerId ? stored.ownerId : null,
    hasDraft: stored.hasDraft === true && preferences.success,
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
      runId: null,
      setOwnerId: (ownerId) => set({ ownerId }),
      setOrigin: (origin) => set({ origin }),
      setPreferences: (preferences) =>
        set({
          preferences: preferencesDraftSchema.parse(preferences),
          hasDraft: true,
        }),
      setRunId: (runId) => set({ runId }),
      reset: () =>
        set({
          ownerId: null,
          hasDraft: false,
          origin: null,
          preferences: defaults,
          runId: null,
        }),
    }),
    {
      name: "food-draft-v1",
      version: 5,
      storage: createJSONStorage(() => safeSessionStorage),
      partialize: ({ ownerId, hasDraft, preferences, origin, runId }) => ({
        ownerId,
        hasDraft,
        preferences,
        origin,
        runId,
      }),
      migrate: () => recoverDraft(null),
      merge: (stored, current) => ({ ...current, ...recoverDraft(stored) }),
    },
  ),
);
