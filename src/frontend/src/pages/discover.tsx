import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, LoaderCircle, MapPin } from "lucide-react";
import { Button } from "../components/ui/button";
import { FoodMap } from "../components/map";
import { PlaceCard } from "../components/place-card";
import { RadiusOptions } from "../components/radius-options";
import { useDraft } from "../lib/store";
import { ApiError, errorMessage, request } from "../lib/api";
import { acceptRecommendation, completeSelection, isDiscardedRun, refreshCurrentRecommendation } from "../lib/recommendations";
import { stream, subscribe } from "../lib/stream";
import {
  runSchema,
  fromDecisionRequest,
  type DecisionEvent,
  type Run,
  type Place,
  type SearchRadius,
} from "../lib/schemas";
import { formatDistance } from "../lib/utils";

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
  const generation = useRef(0);
  const runQuery = useQuery({
    queryKey: ["run", draft.runId],
    queryFn: ({ signal }) =>
      request<Run>(
        "/decision-runs/" + draft.runId,
        undefined,
        "GET",
        undefined,
        signal,
        runSchema,
      ),
    enabled: !!draft.runId && !busy,
    refetchInterval: (q) =>
      polling &&
      q.state.data &&
      ["pending", "running"].includes(q.state.data.status)
        ? 2000
        : false,
    retry: false,
  });
  const sessionId = runQuery.data?.discoverySessionId;
  useEffect(() => {
    if (runQuery.error instanceof ApiError && runQuery.error.code === "RUN_SUPERSEDED" && sessionId)
      void refreshCurrentRecommendation(client, sessionId).catch(() => undefined);
  }, [runQuery.error, sessionId, client]);
  const run = runQuery.error || (draft.runId && isDiscardedRun(client, draft.runId)) ? undefined : runQuery.data;
  const editRequest = (snapshot: Run["request"]) => {
    draft.setPreferences(fromDecisionRequest(snapshot));
    draft.setOrigin(snapshot.origin);
    draft.setRunId(null);
    navigate("/");
  };
  const process = (event: DecisionEvent) => {
    if (event.type === "runStarted" && !isDiscardedRun(client, event.decisionRunId)) draft.setRunId(event.decisionRunId);
    if (event.type === "nodeStarted")
      setSteps((prev) => [
        ...prev.filter((s) => s.node !== event.node),
        { node: event.node, label: event.label, done: false },
      ]);
    if (event.type === "nodeCompleted")
      setSteps((prev) =>
        prev.map((s) => (s.node === event.node ? { ...s, done: true } : s)),
      );
    if (event.type === "result") {
      if (isDiscardedRun(client, event.data.decisionRunId)) return;
      setPolling(false);
      void client.cancelQueries({ queryKey: ["run", event.data.decisionRunId] });
      client.setQueryData<Run>(["run", event.data.decisionRunId], (current) =>
        current?.choice ? current : event.data,
      );
      setSelected(event.data.places?.[0]?.id ?? null);
    }
    if (event.type === "runFailed") {
      setPolling(false);
      setError(errorMessage(event.error.code, event.error.message));
      setPolling(true);
      void client.invalidateQueries({ queryKey: ["run", draft.runId] });
      if (event.error.code === "RUN_SUPERSEDED" && run)
        void refreshCurrentRecommendation(client, run.discoverySessionId).catch(() => undefined);
    }
  };
  const launch = async (
    path: string,
    body: unknown,
    key: string = crypto.randomUUID(),
  ) => {
    if (run?.choice) return;
    const current = ++generation.current;
    const previousId = draft.runId;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setBusy(true);
    setPolling(false);
    setError("");
    setSteps([]);
    setNewRadius(undefined);
    try {
      await stream(path, body, key, controller.signal, (event) => {
        if (!controller.signal.aborted && generation.current === current) process(event);
      }, (accepted) => {
        if (controller.signal.aborted || generation.current !== current) return;
        acceptRecommendation(client, accepted, previousId);
        setSelected(null);
        choiceKeys.current.clear();
      });
    } catch (e) {
      if (!controller.signal.aborted && generation.current === current &&
          !(e instanceof DOMException && e.name === "AbortError")) {
        setPolling(true);
        setError(e instanceof Error ? e.message : "推荐失败");
        if (e instanceof ApiError && e.status === 409 && run)
          await refreshCurrentRecommendation(client, run.discoverySessionId).catch(() => undefined);
      }
    } finally {
      if (abort.current === controller) setBusy(false);
    }
  };
  const processRef = useRef(process);
  processRef.current = process;
  useEffect(() => {
    if (!draft.runId || busy) return;
    const current = ++generation.current;
    const controller = new AbortController();
    void subscribe(draft.runId, controller.signal, (event) => {
      if (!controller.signal.aborted && generation.current === current)
        processRef.current(event);
    }).catch((e) => {
      if (!controller.signal.aborted && generation.current === current &&
          !(e instanceof DOMException && e.name === "AbortError"))
        setError(e instanceof Error ? e.message : "进度读取失败");
    });
    return () => controller.abort();
  }, [draft.runId, busy]);
  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    if (!busy) return;
    const timer = setTimeout(
      () => setError("暂未收到新进度，可等待或恢复查询结果。"),
      25000,
    );
    return () => clearTimeout(timer);
  }, [busy, steps]);
  const refine = (action: string, value: unknown = null) => {
    if (run)
      void launch(`/decision-runs/${run.decisionRunId}/refinements`, {
        action,
        value,
      });
  };
  const choose = async (place: Place) => {
    if (!place.candidateId || !run || run.choice || busy || saving || run.status !== "completed") return;
    setSaving(true);
    try {
      let key = choiceKeys.current.get(place.candidateId);
      if (!key) {
        key = crypto.randomUUID();
        choiceKeys.current.set(place.candidateId, key);
      }
      await request(
        "/place-choices",
        { candidateId: place.candidateId },
        "POST",
        key,
      );
      choiceKeys.current.delete(place.candidateId);
      await completeSelection(client, run.decisionRunId);
      navigate(
        `/decision-runs/${run.decisionRunId}?place=${encodeURIComponent(place.id)}&chosen=1`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
      if (e instanceof ApiError && [404, 409].includes(e.status))
        await refreshCurrentRecommendation(client, run.discoverySessionId).catch(() => undefined);
    } finally {
      setSaving(false);
    }
  };
  const working =
    busy || run?.status === "running" || run?.status === "pending";
  if (run?.choice) {
    const chosen = run.places.find((place) => place.candidateId === run.choice?.candidateId);
    return (
      <>
        <header className="compact-heading">
          <h1>本次选餐已结束</h1>
          <Link to="/history">查看历史</Link>
        </header>
        <section className="empty">
          <Check size={48} />
          <h2>{chosen?.name ?? "已选定餐厅"}</h2>
          <p role="status">选择已保存，可以在历史中回看。</p>
          <Button asChild>
            <Link to={`/decision-runs/${run.decisionRunId}`}>查看已选餐厅</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to="/" onClick={() => draft.setRunId(null)}>开始新的选餐</Link>
          </Button>
        </section>
      </>
    );
  }
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
        {" · 搜索半径 "}
        {formatDistance(
          run?.request.preferences.radiusMeters ??
            draft.preferences.radiusMeters,
        )}
      </p>
      {run?.intent.unhandledRequirements.map((item) => (
        <p className="warning-text" key={item}>
          尚无法核实：{item}
        </p>
      ))}
      {run?.warnings.map((warning) => (
        <p className="warning-text" role="status" key={warning}>{warning}</p>
      ))}
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
                else navigate("/");
              }}
            >
              {draft.runId ? "查询结果" : "重新推荐"}
            </Button>
          )}
        </div>
      )}
      {run?.status === "failed" && (
        <div className="empty">
          <h2>这次还没有选好</h2>
          <p>{errorMessage(run.errorCode ?? "RUN_FAILED", "推荐未完成，请重试。")}</p>
          <Button disabled={busy} onClick={() => void launch(`/decision-runs/${run.decisionRunId}/retry`, {})}>
            按当前条件重试
          </Button>
          <Button
            onClick={() => {
              editRequest(run.request);
            }}
          >
            重新推荐
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
                disabled={working || saving}
                key={action}
                onClick={() => refine(action)}
              >
                {label}
              </button>
            ))}
          </div>
          <details className="hard-constraints">
            <summary>调整预算或搜索范围</summary>
            <fieldset>
              <legend>新的搜索半径</legend>
              <RadiusOptions
                value={newRadius ?? run.request.preferences.radiusMeters}
                onChange={setNewRadius}
                disabled={working || saving}
              />
            </fieldset>
            <Button
              variant="outline"
              disabled={
                working || saving ||
                newRadius === undefined ||
                newRadius === run.request.preferences.radiusMeters
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
                working || saving ||
                newBudget === "" ||
                !Number.isFinite(Number(newBudget)) ||
                Number(newBudget) <
                  Number(run.request.preferences.budgetPerPerson.min ?? 0) ||
                Number(newBudget) > 10000
              }
              onClick={() =>
                refine("changeBudget", {
                  min: run.request.preferences.budgetPerPerson.min,
                  max: newBudget,
                })
              }
            >
              确认修改预算
            </Button>
          </details>
          {!run.places?.length && (
            <section className="empty">
              <h2>附近暂时没有合适的选择</h2>
              <p>我们保留了你的条件，没有自动放宽。</p>
              <p>{run.suggestions.join(" ")}</p>
              <Link to="/">调整预算或搜索范围</Link>
            </section>
          )}
          <div className="candidates">
            {(run.places ?? []).map((place) => (
              <div id={"place-" + place.id} key={place.id}>
                <PlaceCard
                  place={place}
                  selected={selected === place.id}
                  chosen={run.choice?.candidateId === place.candidateId}
                  onSelect={() => setSelected(place.id)}
                  onChoose={() => choose(place)}
                  onExclude={() => refine("excludePlace", place.id)}
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
