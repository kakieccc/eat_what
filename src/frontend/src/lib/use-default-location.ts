import { useEffect } from "react";
import { locate, resolveLocation } from "./amap";
import { useDraft } from "./store";

export function useDefaultLocation(userId: string | undefined) {
  useEffect(() => {
    if (!userId || useDraft.getState().origin) return;
    const controller = new AbortController();
    const current = () => {
      const draft = useDraft.getState();
      return !controller.signal.aborted && draft.ownerId === userId && !draft.origin;
    };
    const initialize = async () => {
      try {
        const point = await locate(controller.signal);
        if (!current()) return;
        const origin = await resolveLocation(point, controller.signal);
        // A manual choice made while locating takes precedence over the default.
        if (current()) useDraft.getState().setOrigin(origin);
      } catch (error) {
        if (!controller.signal.aborted)
          console.warn("Automatic location unavailable; choose a location manually", error);
      }
    };
    void initialize();
    return () => controller.abort();
  }, [userId]);
}
