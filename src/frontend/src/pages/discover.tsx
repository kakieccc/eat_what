import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleDollarSign, MapPin, RefreshCw, SlidersHorizontal, Star, Utensils } from "lucide-react";
import { PageHero } from "../components/brand";
import { Button } from "../components/ui/button";
import { FoodMap } from "../components/map";
import { PlaceCard } from "../components/place-card";
import { RadiusOptions } from "../components/radius-options";
import { useDraft } from "../lib/store";
import { ApiError, errorMessage } from "../lib/api";
import { isDiscardedRun, readRecommendation, useMealBusy } from "../lib/recommendations";
import {
  fromDecisionRequest,
  budgetSchema,
  type Run,
  type Place,
  type SearchRadius,
} from "../lib/schemas";
import { formatBudget, formatDistance } from "../lib/utils";

export function Discover() {
  const draft = useDraft(),
    client = useQueryClient(),
    navigate = useNavigate();
  const [selected, setSelected] = useState<string | null>(null);
  const [showMap, setShowMap] = useState(false);
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
  const preferences = run?.request.preferences ?? draft.preferences;
  const budget = budgetSchema.safeParse({
    min: preferences.budgetPerPerson.min,
    max: newBudget,
  });
  if (run?.choice) {
    return <Navigate to={`/decision-runs/${run.decisionRunId}`} replace />;
  }
  return (
    <>
      <PageHero className="discovery-hero">
        <Link className="back-link" to="/" aria-label="返回首页"><ArrowLeft /></Link>
        <h1>{working ? "正在为你寻找合适的一餐" : "附近，合你心意"}</h1>
        <p className="address-summary">
          <MapPin size={16} />
          {run?.request.origin.address || draft.origin?.address || "尚未确认出发位置"}
        </p>
        <p className="condition-summary">
          {formatDistance(preferences.radiusMeters)} 内 · {formatBudget(preferences.budgetPerPerson)}
          <span>{" · "}{preferences.allowedFoods.length ? preferences.allowedFoods.join("、") : "不限菜系"}</span>
        </p>
        <div className="hero-actions">
          <Button
            variant="outline"
            disabled={working}
            onClick={() => (run ? editRequest(run.request) : navigate("/"))}
          >
            <SlidersHorizontal data-icon="inline-start" />调整条件
          </Button>
          <Button variant="outline" aria-expanded={showMap} aria-controls="recommendation-map" onClick={() => setShowMap(!showMap)}>
            <MapPin data-icon="inline-start" />{showMap ? "收起地图" : "查看地图"}
          </Button>
        </div>
      </PageHero>
      {run?.warnings.map((warning) => (
        <p className="warning-text" role="status" key={warning}>
          {warning}
        </p>
      ))}
      {showMap && <section id="recommendation-map" aria-label="推荐地图"><FoodMap
        origin={run?.request.origin ?? draft.origin}
        places={run?.places ?? []}
        selected={selected}
        onSelect={(id) => {
          setSelected(id);
          document
            .getElementById("place-" + id)
            ?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
        }}
      /></section>}
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
        <section className="recommendation-results" aria-label="推荐结果">
          <div className="refine-row">
            {([
              ["closer", "更近", MapPin],
              ["cheaper", "更便宜", CircleDollarSign],
              ["higherRated", "评分更高", Star],
              ["differentCuisine", "换个口味", Utensils],
              ["refresh", "换一批", RefreshCw],
            ] as const).map(([action, label, Icon]) => (
              <button
                disabled={working}
                key={action}
                onClick={() => refine(action)}
              >
                <Icon size={19} aria-hidden="true" />
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
                step="0.01"
                value={newBudget}
                onChange={(e) => setNewBudget(e.target.value)}
              />
            </label>
            <Button
              variant="outline"
              disabled={
                working ||
                newBudget === "" ||
                !budget.success
              }
              onClick={() =>
                budget.success && refine("changeBudget", budget.data)
              }
            >
              确认修改预算
            </Button>
          </details>
          {!run.places.length && (
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
            {run.places.map((place) => (
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
        </section>
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
