import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, LoaderCircle, MapPin } from "lucide-react";
import { Button } from "../components/ui/button";
import { FoodMap } from "../components/map";
import { PlaceCard } from "../components/place-card";
import { RadiusOptions } from "../components/radius-options";
import { useDraft } from "../lib/store";
import { request } from "../lib/api";
import { stream, subscribe } from "../lib/stream";
import {
  decisionRequestSchema, decisionRequestSnapshotSchema, isSearchRadius, runSchema,
  type DecisionEvent, type Run, type Place, type SearchRadius,
} from "../lib/schemas";
import { formatDistance } from "../lib/utils";

function formatChange(field: string, value: unknown): string {
  if (field === "radiusMeters" && typeof value === "number") return formatDistance(value);
  return Array.isArray(value) ? value.join("、") || "不限" : String(value ?? "不限");
}
export function Discover() {
  const draft = useDraft(),
    client = useQueryClient(),
    navigate = useNavigate(),
    abort = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [polling, setPolling] = useState(true),
    [steps, setSteps] = useState<
      { node: string; label: string; done: boolean }[]
    >([]),
    [selected, setSelected] = useState<string | null>(null),
    [saving, setSaving] = useState(false),
    [newRadius, setNewRadius] = useState<SearchRadius | undefined>(undefined),
    [newBudget, setNewBudget] = useState("60");
  const choiceKeys = useRef(new Map<string, string>());
  const runQuery = useQuery({
    queryKey: ["run", draft.runId],
    queryFn: () => request<Run>("/decision-runs/" + draft.runId, undefined, "GET", undefined, undefined, runSchema),
    enabled: !!draft.runId && polling && !busy,
    refetchInterval: (q) =>
      polling && q.state.data && ["pending", "running"].includes(q.state.data.status)
        ? 2000
        : false,
    retry: false,
  });
  const run = runQuery.data;
  const needsRadiusSelection = !!run && !isSearchRadius(run.request.radiusMeters);
  const editRequest = (snapshot: Run["request"]) => {
    draft.setPreferences(snapshot);
    draft.setOrigin(snapshot.origin);
    draft.setRunId(null);
    navigate("/");
  };
  const process = (event: DecisionEvent) => {
    if (event.type === "runStarted") draft.setRunId(event.decisionRunId);
    if (event.type === "nodeStarted")
      setSteps((prev) => [
        ...prev.filter((s) => s.node !== event.node),
        { node: event.node, label: event.label, done: false },
      ]);
    if (event.type === "nodeCompleted")
      setSteps((prev) =>
        prev.map((s) => (s.node === event.node ? { ...s, done: true } : s)),
      );
    if (event.type === "result" || event.type === "confirmationRequired") {
      setPolling(false);
      client.setQueryData(["run", event.data.decisionRunId], event.data);
      setSelected(event.data.places?.[0]?.id ?? null);
    }
    if (event.type === "runFailed") {
      setPolling(false);
      setError(event.error.message);
    }
  };
  const launch = async (
    path: string,
    body: unknown,
    key: string = crypto.randomUUID(),
  ) => {
    if (path === "/decision-runs") {
      const parsed = decisionRequestSchema.safeParse(body);
      if (!parsed.success) {
        const snapshot = decisionRequestSnapshotSchema.safeParse(body);
        if (snapshot.success) editRequest(snapshot.data);
        else setError("请确认搜索范围、预算和出发位置后重新推荐");
        return;
      }
      body = parsed.data;
    }
    abort.current?.abort();
    if (path === "/decision-runs") draft.setRunId(null);
    const controller = new AbortController();
    abort.current = controller;
    setBusy(true);
    setPolling(false);
    setError("");
    setSteps([]);
    setNewRadius(undefined);
    try {
      await stream(path, body, key, controller.signal, process);
    } catch (e) {
      if (!controller.signal.aborted) {
        setPolling(true);
        setError(e instanceof Error ? e.message : "推荐失败");
      }
    } finally {
      if (abort.current === controller) setBusy(false);
    }
  };
  const launchRef = useRef(launch);
  launchRef.current = launch;
  useEffect(() => {
    const key = sessionStorage.getItem("food-start");
    if (key && draft.origin) {
      sessionStorage.removeItem("food-start");
      void launchRef.current(
        "/decision-runs",
        { ...draft.preferences, origin: draft.origin },
        key,
      );
    }
    return () => abort.current?.abort();
  }, [draft.origin, draft.preferences]);
  useEffect(() => {
    if (!busy) return;
    const timer = setTimeout(
      () => setError("暂未收到新进度，可等待或恢复查询结果。"),
      25000,
    );
    return () => clearTimeout(timer);
  }, [busy, steps]);
  const refine = (action: string, value: unknown = null) => {
    if (run && (action === "changeRadius" || !needsRadiusSelection))
      void launch(`/decision-runs/${run.decisionRunId}/refinements`, {
        action,
        value,
      });
  };
  const resume = async (acceptChanges: boolean) => {
    if (!run) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setBusy(true);
    setError("");
    try {
      const data = await request<Run>(
        `/decision-runs/${run.decisionRunId}`,
        { acceptChanges },
        "PATCH",
        undefined,
        controller.signal,
        runSchema,
      );
      client.setQueryData(["run", run.decisionRunId], data);
      await subscribe(run.decisionRunId, controller.signal, process);
    } catch (e) {
      if (!controller.signal.aborted) {
        setPolling(true);
        setError(e instanceof Error ? e.message : "恢复失败");
      }
    } finally {
      if (abort.current === controller) setBusy(false);
    }
  };
  const choose = async (place: Place) => {
    if (!place.candidateId || !run) return;
    setSaving(true);
    try {
      let key = choiceKeys.current.get(place.candidateId);
      if (!key) {
        key = crypto.randomUUID();
        choiceKeys.current.set(place.candidateId, key);
      }
      await request(
        "/place-choices",
        { candidateId: place.candidateId, feedback: "" },
        "POST",
        key,
      );
      await client.invalidateQueries({ queryKey: ["history"] });
      await client.invalidateQueries({ queryKey: ["run", run.decisionRunId] });
      navigate(
        `/decision-runs/${run.decisionRunId}?place=${encodeURIComponent(place.id)}&chosen=1`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };
  const working =
    busy || run?.status === "running" || run?.status === "pending";
  return (
    <>
      <header className="compact-heading">
        <h1>{working ? "正在为你寻找合适的一餐" : "附近，合你心意"}</h1>
        <Link to="/">调整条件</Link>
      </header>
      <p className="address-summary">
        <MapPin size={16} />
        {run?.request.origin.address ||
          draft.origin?.address ||
          "尚未确认出发位置"}
        {" · 搜索半径 "}{formatDistance(run?.request.radiusMeters ?? draft.preferences.radiusMeters)}
      </p>
      <FoodMap
        origin={run?.request.origin ?? draft.origin}
        places={run?.places ?? []}
        selected={selected}
        onSelect={(id) => {
          setSelected(id);
          document
            .getElementById("place-" + id)
            ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }}
      />
      {steps.length > 0 && (
        <div className="timeline" aria-live="polite">
          {steps.slice(-3).map((s) => (
            <p key={s.node}>
              {s.done ? (
                <Check size={16} />
              ) : (
                <LoaderCircle size={16} className="spin" />
              )}
              {s.label}
            </p>
          ))}
        </div>
      )}
      {(error || runQuery.error) && (
        <div role="alert" className="error">
          {error || runQuery.error?.message}
          {(draft.runId || draft.origin) && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                if (draft.runId) void runQuery.refetch();
                else if (draft.origin)
                  void launch("/decision-runs", {
                    ...draft.preferences,
                    origin: draft.origin,
                  });
              }}
            >
              {draft.runId ? "查询结果" : "重新推荐"}
            </Button>
          )}
        </div>
      )}
      {run?.status === "awaitingConfirmation" && (
        <section className="confirmation">
          <h2>需要你确认条件</h2>
          <p>这段话涉及硬约束变化。是否使用新条件？</p>
          <div>
            {Object.entries(
              run.confirmation ?? {},
            ).map(([field, change]) => (
              <p key={field}>
                <strong>
                  {{
                    radiusMeters: "搜索半径",
                    budgetMax: "预算上限（元）",
                    excludedCuisines: "不想吃的菜系",
                  }[field] ?? "条件"}
                </strong>
                <br />
                {formatChange(field, change.before)}{" "}
                →{" "}
                {formatChange(field, change.after)}
              </p>
            ))}
          </div>
          <div className="card-actions">
            <Button
              disabled={busy}
              variant="outline"
              onClick={() => resume(false)}
            >
              保留原条件
            </Button>
            <Button disabled={busy} onClick={() => resume(true)}>
              使用新条件
            </Button>
          </div>
        </section>
      )}
      {run?.status === "failed" && (
        <div className="empty">
          <h2>这次还没有选好</h2>
          <p>{run.errorCode}</p>
          {run.errorCode === "UNSUPPORTED_RADIUS" && (
            <p>请将补充说明中的距离改为 500 米、1 km、2 km 或 5 km。</p>
          )}
          <Button onClick={() => {
            if (needsRadiusSelection || run.errorCode === "UNSUPPORTED_RADIUS") editRequest(run.request);
            else void launch("/decision-runs", run.request);
          }}>
            {needsRadiusSelection || run.errorCode === "UNSUPPORTED_RADIUS" ? "修改搜索范围" : "重新推荐"}
          </Button>
        </div>
      )}
      {run?.status === "completed" && (
        <>
          <div className="refine-row">
            {[
              ["closer", "更近"],
              ["cheaper", "更便宜"],
              ["higherRated", "评分更高"],
              ["differentCuisine", "换个口味"],
              ["refresh", "换一批"],
            ].map(([action, label]) => (
              <button
                disabled={working || needsRadiusSelection}
                key={action}
                onClick={() => refine(action)}
              >
                {label}
              </button>
            ))}
          </div>
          {needsRadiusSelection && (
            <p className="warning-text" role="alert">
              旧记录的搜索半径为 {formatDistance(run.request.radiusMeters)}，请先选择有效范围再调整推荐。
            </p>
          )}
          <details className="hard-constraints" open={needsRadiusSelection || undefined}>
            <summary>调整预算或搜索范围</summary>
            <fieldset>
              <legend>新的搜索半径</legend>
              <RadiusOptions
                value={newRadius ?? (isSearchRadius(run.request.radiusMeters) ? run.request.radiusMeters : undefined)}
                onChange={setNewRadius}
                disabled={working}
              />
            </fieldset>
            <Button
              variant="outline"
              disabled={
                working ||
                newRadius === undefined ||
                newRadius === run.request.radiusMeters
              }
              onClick={() => refine("changeRadius", newRadius)}
            >
              确认修改搜索范围
            </Button>
            <label className="field-label">
              新的预算上限（元）
              <input
                type="number"
                min={0}
                max={10000}
                value={newBudget}
                onChange={(e) => setNewBudget(e.target.value)}
              />
            </label>
            <Button
              variant="outline"
              disabled={
                working ||
                needsRadiusSelection ||
                newBudget === "" ||
                !Number.isFinite(Number(newBudget)) ||
                Number(newBudget) < 0 ||
                Number(newBudget) > 10000
              }
              onClick={() =>
                refine("changeBudget", { min: null, max: newBudget })
              }
            >
              确认修改预算
            </Button>
          </details>
          {!run.places?.length && (
            <section className="empty">
              <h2>附近暂时没有合适的选择</h2>
              <p>我们保留了你的条件，没有自动放宽。</p>
              <p>
                {Object.entries(run.filterSummary ?? {})
                  .map(([key, value]) => `${key}: ${value}`)
                  .join(" · ")}
              </p>
              <Link to="/">调整预算或搜索范围</Link>
            </section>
          )}
          <div className="candidates">
            {(run.places ?? []).map((place) => (
              <div id={"place-" + place.id} key={place.id}>
                <PlaceCard
                  place={place}
                  selected={selected === place.id}
                  onSelect={() => setSelected(place.id)}
                  onChoose={() => choose(place)}
                  onExclude={needsRadiusSelection ? undefined : () => refine("excludePlace", place.id)}
                  busy={saving || working}
                />
              </div>
            ))}
          </div>
        </>
      )}
      {!run && !working && !error && (
        <div className="empty">
          <h2>从一个出发地点开始</h2>
          <Link to="/">设置本次条件</Link>
        </div>
      )}
    </>
  );
}
