import { useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleDollarSign, MapPin, RefreshCw, SlidersHorizontal, Star, Utensils } from "lucide-react";
import { PageHero } from "../components/brand";
import { DesktopPageHeader } from "../components/desktop-page-header";
import { Button } from "../components/ui/button";
import { FoodMap } from "../components/map";
import { PlaceCard } from "../components/place-card";
import { useDraft } from "../lib/store";
import { useDesktop } from "../lib/use-desktop";
import { ApiError, errorMessage } from "../lib/api";
import { isDiscardedRun, readRecommendation, useMealBusy } from "../lib/recommendations";
import {
  fromDecisionRequest,
  type Run,
  type Place,
} from "../lib/schemas";
import { formatBudget, formatDistance } from "../lib/utils";

export function Discover({ progress }: { progress: ReactNode }) {
  const desktop = useDesktop();
  const draft = useDraft(),
    client = useQueryClient(),
    navigate = useNavigate();
  const [selected, setSelected] = useState<string | null | undefined>();
  const [showMap, setShowMap] = useState(false);
  const busy = useMealBusy();
  const runQuery = useQuery({
    queryKey: ["run", draft.runId],
    queryFn: ({ signal }) => readRecommendation(client, draft.runId!, signal),
    enabled: !!draft.runId,
    retry: false,
  });
  const run =
    draft.job?.kind === "recommendation" || runQuery.error ||
    (draft.runId && isDiscardedRun(client, draft.runId))
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
  const noMatches = run?.status === "completed" && run.places.length === 0;
  const unsuccessful = run?.status === "failed" || noMatches;
  const incompleteSearch = !!(run?.filterSummary.searchFailures || run?.filterSummary.detailFailures);
  const preferences = run?.request.preferences ?? draft.preferences;
  const title = working ? "正在为你寻找合适的一餐" : unsuccessful ? "这次还没有选好" : run?.places.length ? `为你挑了 ${run.places.length} 家` : "附近，合你心意";
  const address = run?.request.origin.address || draft.origin?.address || "尚未确认出发位置";
  const activeId = selected === null ? null : run?.places.find((place) => place.id === selected)?.id ?? run?.places[0]?.id;
  const meal = run?.request ?? draft.preferences;
  const conditions = <>
    <span>{formatBudget(preferences.budgetPerPerson)}</span>
    <span>{formatDistance(preferences.radiusMeters)}</span>
    <span>{({ breakfast: "早餐", lunch: "午餐", dinner: "晚餐", lateNight: "夜宵" })[meal.mealPeriod]} · {meal.partySize} 人</span>
    {preferences.allowedFoods.length > 0 && <span>{preferences.allowedFoods.join("、")}</span>}
    {meal.requestText && <span className="request-chip" title={meal.requestText}>{meal.requestText}</span>}
  </>;
  const actions = <div className="hero-actions">
    <Button variant="outline" disabled={working} onClick={() => (run ? editRequest(run.request) : navigate("/"))}>
      <SlidersHorizontal data-icon="inline-start" />调整条件
    </Button>
    {!desktop && <Button variant="outline" aria-expanded={showMap} aria-controls="recommendation-map" onClick={() => setShowMap(!showMap)}>
      <MapPin data-icon="inline-start" />{showMap ? "收起地图" : "查看地图"}
    </Button>}
  </div>;
  const map = <FoodMap
    origin={run?.request.origin ?? draft.origin}
    places={run?.places ?? []}
    selected={activeId}
    radiusMeters={preferences.radiusMeters}
    onSelect={(id) => {
      setSelected(id);
      document.getElementById("place-" + id)?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest",
      });
    }}
  />;
  if (run?.choice) {
    return <Navigate to={`/decision-runs/${run.decisionRunId}`} replace />;
  }
  return (
    <>
      {!desktop && <PageHero className="discovery-hero">
        <Link className="back-link" to="/" aria-label="返回首页"><ArrowLeft /></Link>
        <h1>{title}</h1>
        <p className="address-summary">
          <MapPin size={16} />
          {address}
        </p>
        <div className="condition-chips">
          {conditions}
        </div>
        {actions}
        {!unsuccessful && progress}
      </PageHero>}
      {!unsuccessful && run?.warnings.map((warning) => (
        <p className="warning-text" role="status" key={warning}>
          {warning}
        </p>
      ))}
      {!desktop && showMap && <section id="recommendation-map" aria-label="推荐地图">{map}</section>}
      <div className={desktop ? "desktop-discovery-layout" : undefined}>
      <div className={desktop ? "desktop-results-list" : undefined}>
      {desktop && <>
        <DesktopPageHeader title={title} description={<span className="desktop-origin"><MapPin size={17} aria-hidden="true" />{address}</span>}>
          {actions}
        </DesktopPageHeader>
        <div className="condition-chips">{conditions}</div>
        {!unsuccessful && progress}
      </>}
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
      {unsuccessful && run && (
        <section className="empty" role="alert" aria-label="选餐提示">
          <p>
            {run.status === "failed"
              ? errorMessage(run.errorCode ?? "RUN_FAILED", "本次推荐意外中断，请稍后重试。")
              : incompleteSearch
                ? "部分餐厅信息未能获取，本次搜索不完整，暂时无法确认是否有合适的餐厅。请稍后重试。"
                : run.suggestions.join(" ") || "当前范围和用餐条件下暂未找到合适餐厅，可以调整预算、搜索范围或食物条件后重试。"}
          </p>
          {noMatches && !incompleteSearch && <p>已保留你的条件，没有自动放宽。</p>}
          {(run.status === "failed" || incompleteSearch) && <Button
            disabled={busy}
            onClick={() =>
              run.status === "failed"
                ? launch(`/decision-runs/${run.decisionRunId}/retry`, {})
                : refine("refresh")
            }
          >
            按当前条件重试
          </Button>}
          <Button
            disabled={busy}
            onClick={() => {
              editRequest(run.request);
            }}
          >
            调整用餐条件
          </Button>
        </section>
      )}
      {run?.status === "completed" && run.places.length > 0 && (
        <section className="recommendation-results" aria-label="推荐结果">
          <div className="results-heading">
            <h2>附近餐厅</h2>
            <div className="results-controls">
              <Button variant="outline" disabled={working} onClick={() => refine("refresh")}><RefreshCw data-icon="inline-start" />换一批</Button>
            </div>
          </div>
          <div className="refine-row">
            {([
              ["closer", "更近", MapPin],
              ["cheaper", "更便宜", CircleDollarSign],
              ["higherRated", "评分更高", Star],
              ["differentCuisine", "换个口味", Utensils],
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
          <div className="candidates">
            {run.places.map((place) => (
              <div id={"place-" + place.id} key={place.id}>
                <PlaceCard
                  place={place}
                  selected={activeId === place.id}
                  onSelect={() => setSelected(activeId === place.id ? null : place.id)}
                  onChoose={() => choose(place)}
                  onExclude={() => refine("excludePlace", place.id)}
                  busy={working}
                />
              </div>
            ))}
          </div>
        </section>
      )}
      {!run && !draft.job && !working && !runQuery.error && (
        <div className="empty">
          <h2>从一个出发地点开始</h2>
          <Link to="/">设置本次条件</Link>
        </div>
      )}
      </div>
      {desktop && <aside id="recommendation-map" className="desktop-results-map" aria-label="推荐地图">
        <header><h2>附近餐厅</h2></header>
        {map}
      </aside>}
      </div>
    </>
  );
}
