import type { QueryClient } from "@tanstack/react-query";
import { useDraft } from "./store";
import { request } from "./api";
import { runSchema, type Run } from "./schemas";

const discarded = new WeakMap<QueryClient, Set<string>>();
const channelName = "food-current-recommendation";
export const isDiscardedRun = (client: QueryClient, id: string) => discarded.get(client)?.has(id) ?? false;

function discard(client: QueryClient, id: string) {
  const ids = discarded.get(client) ?? new Set<string>();
  ids.add(id);
  discarded.set(client, ids);
  void client.cancelQueries({ queryKey: ["run", id] });
  client.setQueryData<Run>(["run", id], (old) => old ? { ...old, places: [], choice: null } : undefined);
  client.removeQueries({ queryKey: ["run", id] });
}

export function acceptRecommendation(client: QueryClient, run: Run, previousId?: string | null) {
  if (isDiscardedRun(client, run.decisionRunId)) return;
  for (const [key, cached] of client.getQueriesData<Run>({ queryKey: ["run"] })) {
    if (cached?.discoverySessionId === run.discoverySessionId && key[1] !== run.decisionRunId)
      discard(client, cached.decisionRunId);
  }
  if (previousId && previousId !== run.decisionRunId) discard(client, previousId);
  client.setQueryData(["run", run.decisionRunId], run);
  client.removeQueries({ queryKey: ["history"] });
  if (typeof BroadcastChannel !== "undefined") {
    const channel = new BroadcastChannel(channelName);
    channel.postMessage({ previousId, runId: run.decisionRunId });
    channel.close();
  }
}

export async function refreshCurrentRecommendation(client: QueryClient, sessionId: string) {
  const runs = await request<Run[]>(`/discovery-sessions/${sessionId}/decision-runs`);
  if (!runs[0]) return;
  const current = runSchema.parse(runs[0]);
  acceptRecommendation(client, current);
  useDraft.getState().setRunId(current.decisionRunId);
}

export function watchRecommendations(client: QueryClient) {
  if (typeof BroadcastChannel === "undefined") return () => {};
  const channel = new BroadcastChannel(channelName);
  channel.onmessage = (event: MessageEvent<unknown>) => {
    const data = event.data;
    if (!data || typeof data !== "object" || !("previousId" in data) || !("runId" in data) ||
        typeof data.previousId !== "string" || typeof data.runId !== "string" ||
        data.previousId === data.runId) return;
    const oldId = data.previousId;
    const known = !!client.getQueryData(["run", oldId]) || useDraft.getState().runId === oldId;
    if (!known) return;
    discard(client, oldId);
    client.removeQueries({ queryKey: ["history"] });
    if (useDraft.getState().runId === oldId) useDraft.getState().setRunId(data.runId);
  };
  return () => channel.close();
}
