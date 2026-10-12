import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowUpRight, ClipboardList, MapPin } from "lucide-react";
import { Button } from "../components/ui/button";
import { FoodMap } from "../components/map";
import { request } from "../lib/api";
import { useDraft } from "../lib/store";
import { defaults, runSchema, type Place, type PreferencesSnapshot, type Run } from "../lib/schemas";
import { formatDistance, navigationHref } from "../lib/utils";
import { useParams, useSearchParams } from "react-router-dom";
type HistoryData = {
  items: {
    id: string;
    createdAt: string;
    request: PreferencesSnapshot;
    choices: {
      id: string;
      feedback: string;
      decisionRunId: string;
      place: Place;
    }[];
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
              {item.choices.length === 0 ? (
                <p>本次尚未选择餐厅</p>
              ) : (
                item.choices.map((choice) => (
                  <Link
                    key={choice.id}
                    to={`/decision-runs/${choice.decisionRunId}?place=${choice.place.id}`}
                  >
                    <h2>
                      {choice.place.name}
                      <ArrowUpRight size={18} />
                    </h2>
                    <p>
                      {choice.place.cuisineTypes.join(" · ")} ·{" "}
                      直线 {formatDistance(choice.place.straightLineDistanceMeters)}
                    </p>
                    {choice.feedback && <p>{choice.feedback}</p>}
                  </Link>
                ))
              )}
              <button
                className="text-button"
                onClick={() => {
                  draft.setPreferences({
                    ...defaults,
                    ...item.request,
                    budgetPerPerson: {
                      min: item.request.budgetPerPerson?.min ?? null,
                      max: item.request.budgetPerPerson?.max ?? null,
                    },
                  });
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
  const client = useQueryClient();
  const { runId } = useParams(),
    [params] = useSearchParams(),
    [error, setError] = useState(""),
    [feedback, setFeedback] = useState(""),
    [savedLocally, setSaved] = useState(false),
    [busy, setBusy] = useState(false),
    [key] = useState(() => crypto.randomUUID());
  const query = useQuery({
    queryKey: ["run", runId],
    queryFn: () => request<Run>("/decision-runs/" + runId, undefined, "GET", undefined, undefined, runSchema),
    retry: false,
  });
  const run = query.data,
    place =
      run?.places?.find((p) => p.id === params.get("place")) ??
      run?.places?.[0];
  const saved =
    savedLocally ||
    !!(
      place?.candidateId && run?.chosenCandidateIds?.includes(place.candidateId)
    );
  const save = async () => {
    if (!place?.candidateId) return;
    setBusy(true);
    try {
      await request(
        "/place-choices",
        { candidateId: place.candidateId, feedback },
        "POST",
        key,
      );
      await client.invalidateQueries({ queryKey: ["history"] });
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };
  const navigation = navigationHref(place?.navigationUrl);
  return (
    <>
      <header className="compact-heading">
        <Link to="/discover" aria-label="返回推荐">
          <ArrowLeft />
        </Link>
        <h1>用餐决策详情</h1>
      </header>
      {query.isPending ? (
        <p>正在读取这次选择…</p>
      ) : query.isError ? (
        <p className="error" role="alert">
          {query.error.message}
        </p>
      ) : place && run ? (
        <>
          <h2 className="detail-name">{place.name}</h2>
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
            距出发位置直线 {formatDistance(place.straightLineDistanceMeters)}，实际道路距离可能更长。
          </p>
          {place.warnings?.map((w) => (
            <p className="warning-text" key={w}>
              {w}
            </p>
          ))}
          {!saved && (
            <>
              <label className="field-label">
                这次选择的想法（可选）
                <textarea
                  rows={2}
                  maxLength={300}
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                />
              </label>
              <Button className="primary-full" disabled={busy} onClick={save}>
                保存这次选择
              </Button>
            </>
          )}
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
          {saved && (
            <p role="status" className="footnote">
              选择已保存，可以在历史中回看。
            </p>
          )}
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
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}
