import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import {
  defaults, originSchema, preferencesSnapshotSchema, type Origin, type PreferencesSnapshot,
} from "./schemas";
interface Draft {
  hasDraft: boolean;
  origin: Origin | null;
  preferences: PreferencesSnapshot;
  runId: string | null;
  setOrigin: (origin: Origin | null) => void;
  setPreferences: (preferences: PreferencesSnapshot) => void;
  setRunId: (runId: string | null) => void;
  reset: () => void;
}

function recoverDraft(value: unknown) {
  const stored = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const preferences = preferencesSnapshotSchema.safeParse(stored.preferences);
  const origin = originSchema.safeParse(stored.origin);
  return {
    hasDraft: stored.hasDraft === true,
    preferences: preferences.success ? preferences.data : defaults,
    origin: origin.success ? origin.data : null,
    runId: typeof stored.runId === "string" ? stored.runId : null,
  };
}
export const useDraft = create<Draft>()(
  persist(
    (set) => ({
      hasDraft: false,
      origin: null,
      preferences: defaults,
      runId: null,
      setOrigin: (origin) => set({ origin }),
      setPreferences: (preferences) => set({
        preferences: preferencesSnapshotSchema.parse(preferences), hasDraft: true,
      }),
      setRunId: (runId) => set({ runId }),
      reset: () => set({ hasDraft: false, origin: null, preferences: defaults, runId: null }),
    }),
    {
      name: "food-draft-v1",
      version: 2,
      storage: createJSONStorage(() => sessionStorage),
      partialize: ({ hasDraft, preferences, origin, runId }) => ({ hasDraft, preferences, origin, runId }),
      migrate: (stored) => recoverDraft(stored),
      merge: (stored, current) => ({ ...current, ...recoverDraft(stored) }),
    },
  ),
);
