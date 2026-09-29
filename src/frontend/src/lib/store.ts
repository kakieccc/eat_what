import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { defaults, type Origin, type Preferences } from "./schemas";
interface Draft {
  hasDraft: boolean;
  origin: Origin | null;
  preferences: Preferences;
  runId: string | null;
  setOrigin: (origin: Origin | null) => void;
  setPreferences: (preferences: Preferences) => void;
  setRunId: (runId: string | null) => void;
  reset: () => void;
}
export const useDraft = create<Draft>()(
  persist(
    (set) => ({
      hasDraft: false,
      origin: null,
      preferences: defaults,
      runId: null,
      setOrigin: (origin) => set({ origin }),
      setPreferences: (preferences) => set({ preferences, hasDraft: true }),
      setRunId: (runId) => set({ runId }),
      reset: () => set({ hasDraft: false, origin: null, preferences: defaults, runId: null }),
    }),
    { name: "food-draft-v1", storage: createJSONStorage(() => sessionStorage) },
  ),
);
