import { Link, useNavigate } from "react-router-dom";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { ArrowLeft, ArrowUpRight, ClipboardList, MapPin } from "lucide-react";
import { Button } from "../components/ui/button";
import { FoodMap } from "../components/map";
import { ApiError, request } from "../lib/api";
import { isDiscardedRun } from "../lib/recommendations";
import { useDraft } from "../lib/store";
import {
  fromDecisionRequest,
  runSchema,
  type Place,
  type DecisionRequest,
  type Run,
} from "../lib/schemas";
import { formatDistance, navigationHref } from "../lib/utils";
import { useParams } from "react-router-dom";
type HistoryData = {
  items: {
    id: string;
    createdAt: string;
    request: DecisionRequest;
    choice: {
      id: string;
      decisionRunId: string;
      place: Place;
    };
  }[];
  nextCursor?: string | null;
};
export function History() {
  const navigate = useNavigate(),
    draft = useDraft();
  const query = useInfiniteQuery({
    queryKey: ["history"],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      request<HistoryData>(
        "/discovery-sessions" +
          (pageParam ? "?cursor=" + encodeURIComponent(pageParam) : ""),
      ),
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    retry: false,
  });
  const items = query.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <header className="page-heading">
        <h1>每一餐，都有迹可循</h1>
        <p>记下选择，让下一次更轻松。</p>
      </header>
      {query.isPending ? (
        <p>正在读取历史…</p>
      ) : query.isError ? (
        <div role="alert" className="error">
          {query.error.message}
          <Button variant="outline" onClick={() => query.refetch()}>
            重试
          </Button>
        </div>
      ) : items.length === 0 ? (
        <section className="empty history-empty">
          <ClipboardList size={58} />
          <h2>还没有用餐记录</h2>
          <p>
            当你做出用餐决定，
            <br />
            这一餐就会留在这里。
          </p>
          <Button onClick={() => navigate("/")}>去选今天的第一餐</Button>
        </section>
      ) : (
        <div className="history-list">
          {items.map((item) => (
            <article key={item.id}>
              <time>
                {new Date(item.createdAt).toLocaleString("zh-CN", {
                  timeZone: "Asia/Shanghai",
                })}
              </time>
              <Link
                to={`/decision-runs/${item.choice.decisionRunId}?place=${item.choice.place.id}`}
              >
                <h2>
                  {item.choice.place.name}
                  <ArrowUpRight size={18} />
                </h2>
                <p>
                  {item.choice.place.cuisineTypes.join(" · ")} · 直线{" "}
                  {formatDistance(item.choice.place.straightLineDistanceMeters)}
                </p>
              </Link>
              <button
                className="text-button"
                onClick={() => {
                  draft.initialize({
                    ...fromDecisionRequest(item.request),
                    requestText: "",
                  }, "history", null);
                  draft.setRunId(null);
                  draft.setOrigin(null);
                  navigate("/map");
                }}
              >
                按类似条件再选一次
              </button>
            </article>
          ))}
          {query.hasNextPage && (
            <Button
              variant="outline"
              disabled={query.isFetchingNextPage}
              onClick={() => query.fetchNextPage()}
            >
              加载更多
            </Button>
          )}
        </div>
      )}
    </>
  );
}
export function Detail() {
  const client = useQueryClient(),
    draft = useDraft();
  const { runId } = useParams();
  const query = useQuery({
    queryKey: ["run", runId],
    queryFn: ({ signal }) =>
      request<Run>(
        "/decision-runs/" + runId,
        undefined,
        "GET",
        undefined,
        signal,
        runSchema,
      ),
    retry: false,
  });
  const run = query.error || (runId && isDiscardedRun(client, runId)) ? undefined : query.data,
    place = run?.choice
      ? run.places.find((p) => p.candidateId === run.choice?.candidateId)
      : undefined;
  const superseded = query.error instanceof ApiError && query.error.code === "RUN_SUPERSEDED";
  const navigation = navigationHref(place?.navigationUrl);
  return (
    <>
      <header className="compact-heading">
        <Link to="/history" aria-label="返回历史">
          <ArrowLeft />
        </Link>
        <h1>用餐决策详情</h1>
      </header>
      {query.isPending ? (
        <p>正在读取这次选择…</p>
      ) : query.isError ? (
        <div className="error" role="alert">
          <p>{superseded ? "这批推荐已被替换，请从历史查看已完成的选餐，或返回首页重新选餐。" : query.error.message}</p>
          {superseded && <Link to="/history">查看历史</Link>}
        </div>
      ) : place && run ? (
        <>
          <h2 className="detail-name">{place.name}</h2>
          {run.warnings.map((warning) => (
            <p className="warning-text" role="status" key={warning}>{warning}</p>
          ))}
          <p className="muted">
            {place.cuisineTypes.join(" · ")} ·{" "}
            {place.averageCost
              ? `参考人均 ¥${place.averageCost}`
              : "人均暂无数据"}
          </p>
          <FoodMap
            origin={run.request.origin}
            places={[place]}
            selected={place.id}
          />
          <p className="address-summary">
            <MapPin size={16} />
            {place.address}
          </p>
          <p className="reason">{place.reason}</p>
          <p>
            距出发位置直线 {formatDistance(place.straightLineDistanceMeters)}
            ，实际道路距离可能更长。
          </p>
          {place.warnings?.map((w) => (
            <p className="warning-text" key={w}>
              {w}
            </p>
          ))}
          <p role="status" className="footnote">
            本次选餐已结束，选择已保存，可以在历史中回看。
          </p>
          {navigation && (
            <a
              className="navigation-button"
              href={navigation}
              target="_blank"
              rel="noopener noreferrer"
            >
              在高德查看
              <ArrowUpRight size={18} />
            </a>
          )}
          <Button variant="outline" asChild>
            <Link to="/" onClick={() => draft.startNewMeal()}>开始新的选餐</Link>
          </Button>
          <p className="data-source">
            来源：高德地图 ·{" "}
            {new Date(place.dataUpdatedAt).toLocaleString("zh-CN", {
              timeZone: "Asia/Shanghai",
            })}
          </p>
        </>
      ) : (
        <section className="empty">
          <ClipboardList size={48} />
          <h2>尚未选择餐厅</h2>
          <Link to="/">去选一餐</Link>
        </section>
      )}
    </>
  );
}
