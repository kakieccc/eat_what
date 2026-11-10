import { Link, useNavigate } from "react-router-dom";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { ArrowLeft, ArrowUpRight, ChevronRight, ClipboardList, MapPin } from "lucide-react";
import { PageHero } from "../components/brand";
import { DesktopPageHeader } from "../components/desktop-page-header";
import { Button } from "../components/ui/button";
import { FoodMap } from "../components/map";
import { PlaceFacts } from "../components/place-facts";
import { ApiError, request } from "../lib/api";
import { isDiscardedRun, useMealBusy } from "../lib/recommendations";
import { useDraft } from "../lib/store";
import { useDesktop } from "../lib/use-desktop";
import {
  fromDecisionRequest,
  historySchema,
  runSchema,
  type DecisionRequest,
} from "../lib/schemas";
import { formatDistance } from "../lib/utils";
import { useParams } from "react-router-dom";
export function History() {
  const desktop = useDesktop();
  const navigate = useNavigate(),
    draft = useDraft();
  const busy = useMealBusy();
  const query = useInfiniteQuery({
    queryKey: ["history"],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      request(
        "/discovery-sessions" +
          (pageParam ? "?cursor=" + encodeURIComponent(pageParam) : ""),
        undefined, "GET", undefined, signal, historySchema,
      ),
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    retry: false,
  });
  const items = query.data?.pages.flatMap((p) => p.items) ?? [];
  const repeatMeal = (request: DecisionRequest) => {
    draft.initialize({ ...fromDecisionRequest(request), requestText: "" }, "history", null);
    draft.setRunId(null);
    draft.setOrigin(null);
    navigate("/map");
  };
  return (
    <>
      {desktop ? <DesktopPageHeader title="用餐历史" description="回看每一次选择，也可以按相似条件再选一餐。" /> : <PageHero className="history-hero"><h1>用餐历史</h1></PageHero>}
      {busy && <p role="status">当前任务尚未完成或待确认，可以继续查看历史。</p>}
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
          <Button onClick={() => navigate("/")}>去选今天的第一餐</Button>
        </section>
      ) : desktop ? (
        <div className="desktop-history">
          <table>
            <caption className="sr-only">用餐记录</caption>
            <thead><tr><th scope="col">用餐时间</th><th scope="col">餐厅</th><th scope="col">菜系 / 距离</th><th scope="col">参考人均</th><th scope="col">操作</th></tr></thead>
            <tbody>{items.map((item) => <tr key={item.id}>
              <td><time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</time></td>
              <td><Link className="history-place-link" to={`/decision-runs/${item.choice.decisionRunId}?place=${item.choice.place.id}`}>
                {item.choice.place.name}<ChevronRight size={16} />
              </Link></td>
              <td>{item.choice.place.cuisineTypes.join(" · ")}<span className="history-distance">直线 {formatDistance(item.choice.place.straightLineDistanceMeters)}</span></td>
              <td>{item.choice.place.averageCost === null ? "暂无数据" : `¥${item.choice.place.averageCost}`}</td>
              <td><button className="text-button" disabled={busy} onClick={() => repeatMeal(item.request)}>按类似条件再选</button></td>
            </tr>)}</tbody>
          </table>
          {query.hasNextPage && <Button variant="outline" disabled={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>加载更多</Button>}
        </div>
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
                  <ChevronRight size={22} />
                </h2>
                <p>
                  {item.choice.place.cuisineTypes.join(" · ")} · 直线{" "}
                  {formatDistance(item.choice.place.straightLineDistanceMeters)}
                </p>
              </Link>
              <button
                className="text-button"
                disabled={busy}
                onClick={() => repeatMeal(item.request)}
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
  const desktop = useDesktop();
  const client = useQueryClient(),
    draft = useDraft(),
    navigate = useNavigate();
  const busy = useMealBusy();
  const { runId } = useParams();
  const query = useQuery({
    queryKey: ["run", runId],
    queryFn: ({ signal }) =>
      request(
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
  const navigation = place?.navigationUrl;
  const map = place && run && <FoodMap origin={run.request.origin} places={[place]} selected={place.id} />;
  return (
    <>
      {!place && <header className="compact-heading">
        <Link to="/history" aria-label="返回历史">
          <ArrowLeft />
        </Link>
        <h1>用餐决策详情</h1>
      </header>}
      {query.isPending ? (
        <p>正在读取这次选择…</p>
      ) : query.isError ? (
        <div className="error" role="alert">
          <p>{superseded ? "这批推荐已被替换，请从历史查看已完成的选餐，或返回首页重新选餐。" : query.error.message}</p>
          {superseded && <Link to="/history">查看历史</Link>}
        </div>
      ) : place && run ? (
        <section className="place-detail">
          {desktop ? <DesktopPageHeader title={place.name}>
            <Button variant="outline" asChild><Link to="/history"><ArrowLeft data-icon="inline-start" />返回历史</Link></Button>
          </DesktopPageHeader> : <PageHero className="detail-hero">
            <Link className="back-link" to="/history" aria-label="返回历史"><ArrowLeft /><span>这一餐，选好了</span></Link>
            <h1>{place.name}</h1>
          </PageHero>}
          <div className={desktop ? "desktop-detail-layout" : undefined}>
          <div className={desktop ? "desktop-detail-info" : undefined}>
          {run.warnings.map((warning) => (
            <p className="warning-text" role="status" key={warning}>{warning}</p>
          ))}
          <PlaceFacts place={place} />
          {!desktop && map}
          <p className="address-summary">
            <MapPin size={16} />
            {place.address}
          </p>
          <p className="distance-note">
            距出发位置直线 {formatDistance(place.straightLineDistanceMeters)}
            ，实际道路距离可能更长。
          </p>
          {place.warnings.map((w) => (
            <p className="warning-text" key={w}>
              {w}
            </p>
          ))}
          <p role="status" className="footnote">
            已保存，可在历史中回看。
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
          <Button className="new-meal" variant="ghost" disabled={busy} onClick={() => {
            draft.startNewMeal();
            navigate("/");
          }}>
            开始新的选餐
          </Button>
          <p className="data-source">
            来源：高德地图 ·{" "}
            {new Date(place.dataUpdatedAt).toLocaleString("zh-CN", {
              timeZone: "Asia/Shanghai",
            })}
          </p>
          </div>
          {desktop && <aside className="desktop-results-map desktop-detail-map" aria-label="餐厅位置">
            <header><h2>餐厅位置</h2></header>
            {map}
          </aside>}
          </div>
        </section>
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
