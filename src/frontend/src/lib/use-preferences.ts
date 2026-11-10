import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { configError, request } from "./api";
import { accountPreferencesSchema, defaults } from "./schemas";
import { useDraft } from "./store";

const readPreferences = () =>
  request("/preferences", undefined, "GET", undefined, undefined, accountPreferencesSchema);

export function usePreferences() {
  return useQuery({
    queryKey: ["preferences"],
    queryFn: readPreferences,
    enabled: !configError,
    retry: false,
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
  });
}

export function usePreferencePrefill() {
  const saved = usePreferences();
  const draft = useDraft();
  useEffect(() => {
    if (saved.isFetching || (!saved.data && !saved.isError && !configError)) return;
    if (!draft.hasDraft) {
      draft.initialize({ ...defaults, ...saved.data?.defaults }, "defaults", saved.data?.revision ?? null);
    } else if (
      saved.data && draft.prefill?.source === "defaults" &&
      draft.prefill.revision !== saved.data.revision
    ) {
      draft.initialize({ ...draft.preferences, ...saved.data.defaults }, "defaults", saved.data.revision);
    }
  }, [draft, saved.data, saved.isError, saved.isFetching]);
  return saved;
}
