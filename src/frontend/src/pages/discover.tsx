import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, MapPin } from "lucide-react";
import { Button } from "../components/ui/button";
import { FoodMap } from "../components/map";
import { PlaceCard } from "../components/place-card";
import { RadiusOptions } from "../components/radius-options";
import { useDraft } from "../lib/store";
import { ApiError, errorMessage } from "../lib/api";
import { isDiscardedRun, readRecommendation, useMealBusy } from "../lib/recommendations";
import {
  fromDecisionRequest,
  type Run,
  type Place,
  type SearchRadius,
} from "../lib/schemas";
import { formatDistance } from "../lib/utils";

export function Discover() {
  const draft = useDraft(),
    client = useQueryClient(),
    navigate = useNavigate();
  const [selected, setSelected] = useState<string | null>(null);
  const [newRadius, setNewRadius] = useState<SearchRadius | undefined>(
    undefined,
  );
  const [newBudget, setNewBudget] = useState("60");
  const busy = useMealBusy();
  const runQuery = useQuery({
    queryKey: ["run", draft.runId],
    queryFn: ({ signal }) => readRecommendation(client, draft.runId!, signal),
    enabled: !!draft.runId,
    retry: false,
  });
  const run =
    runQuery.error || (draft.runId && isDiscardedRun(client, draft.runId))
      ? undefined
      : runQuery.data;
  const editRequest = (snapshot: Run["request"]) => {
    if (draft.prefill) draft.setPreferences(fromDecisionRequest(snapshot));
    else draft.initialize(fromDecisionRequest(snapshot), "history", null);
    draft.setOrigin(snapshot.origin);
    draft.setRunId(null);
    navigate("/");
  };
  const launch = (path: string, body: Record<string, unknown>) => {
    if (!run || run.choice || busy) return;
    draft.enqueue("recommendation", path, body, run.decisionRunId);
    setNewRadius(undefined);
  };
  const refine = (action: string, value: unknown = null) => {
    if (run)
      launch(`/decision-runs/${run.decisionRunId}/refinements`, {
        action,
        value,
      });
  };
  const choose = (place: Place) => {
    if (
      !place.candidateId ||
      !run ||
      run.choice ||
      busy ||
      run.status !== "completed"
    )
      return;
    draft.enqueue(
      "choice",
      "/place-choices",
      { candidateId: place.candidateId },
      run.decisionRunId,
    );
  };
  const working =
    busy || run?.status === "running" || run?.status === "pending";
  if (run?.choice) {
    const chosen = run.places.find(
      (place) => place.candidateId === run.choice?.candidateId,
    );
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
          <Button variant="outline" disabled={busy} onClick={() => {
            draft.startNewMeal();
            navigate("/");
          }}>
            开始新的选餐
          </Button>
        </section>
      </>
    );
  }
  return (
    <>
      <header className="compact-heading">
        <h1>{working ? "正在为你寻找合适的一餐" : "附近，合你心意"}</h1>
        <Button
          variant="ghost"
          disabled={working}
          onClick={() => (run ? editRequest(run.request) : navigate("/"))}
        >
          调整条件
        </Button>
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
      {run?.warnings.map((warning) => (
        <p className="warning-text" role="status" key={warning}>
          {warning}
        </p>
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
      {runQuery.error instanceof ApiError &&
        runQuery.error.code === "WORKFLOW_UPGRADED" && (
          <Button
            disabled={busy}
            onClick={() => {
              draft.startNewMeal();
              navigate("/");
            }}
          >
            开始新的选餐
          </Button>
        )}
      {run?.status === "failed" && (
        <div className="empty">
          <h2>这次还没有选好</h2>
          <p>
            {errorMessage(
              run.errorCode ?? "RUN_FAILED",
              "推荐未完成，请重试。",
            )}
          </p>
          <Button
            disabled={busy}
            onClick={() =>
              void launch(`/decision-runs/${run.decisionRunId}/retry`, {})
            }
          >
            按当前条件重试
          </Button>
          <Button
            disabled={busy}
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
                disabled={working}
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
                disabled={working}
              />
            </fieldset>
            <Button
              variant="outline"
              disabled={
                working ||
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
                working ||
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
              <Button variant="ghost" onClick={() => editRequest(run.request)}>
                调整预算或搜索范围
              </Button>
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
                  onExclude={() => refine("excludePlace", place.id)}
                  busy={working}
                />
              </div>
            ))}
          </div>
        </>
      )}
      {!run && !working && !runQuery.error && (
        <div className="empty">
          <h2>从一个出发地点开始</h2>
          <Link to="/">设置本次条件</Link>
        </div>
      )}
    </>
  );
}
