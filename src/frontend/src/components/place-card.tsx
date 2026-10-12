import { MapPin, Star, ArrowUpRight } from "lucide-react";
import type { Place } from "../lib/schemas";
import { cn, formatDistance, navigationHref } from "../lib/utils";
import { Button } from "./ui/button";
export function PlaceCard({
  place,
  selected,
  onSelect,
  onChoose,
  onExclude,
  busy = false,
}: {
  place: Place;
  selected: boolean;
  onSelect: () => void;
  onChoose: () => void;
  onExclude?: () => void;
  busy?: boolean;
}) {
  const navigation = navigationHref(place.navigationUrl);
  return (
    <article
      className={cn("place-card", { selected })}
      onFocus={onSelect}
    >
      <button className="place-title" onClick={onSelect}>
        <span className="rank">{place.rank}</span>
        <h2>{place.name}</h2>
        <ArrowUpRight size={18} />
      </button>
      <p className="muted">{place.cuisineTypes.join(" · ")}</p>
      <div className="place-stats">
        <span>
          <MapPin size={16} />
          直线 {formatDistance(place.straightLineDistanceMeters)}
        </span>
        <span>
          <Star size={15} />
          {place.rating ?? "暂无数据"}
        </span>
        <span>
          {place.averageCost !== null && place.averageCost !== undefined
            ? `¥${place.averageCost}/人`
            : "人均暂无数据"}
        </span>
      </div>
      <p className="reason">{place.reason}</p>
      <p className="muted">
        {place.businessStatus === "open"
          ? "营业中"
          : place.businessStatus === "closed"
            ? "已关闭"
            : "营业状态未知"}
        {place.openingHoursText ? ` · ${place.openingHoursText}` : ""}
      </p>
      {place.warnings?.map((w) => (
        <p className="warning-text" key={w}>
          {w}
        </p>
      ))}
      <details>
        <summary>为什么推荐 · 评分明细</summary>
        {Object.entries(place.scoreBreakdown ?? {}).map(([key, value]) => (
          <div className="score-line" key={key}>
            <span>
              {{
                preference_match: "口味匹配",
                distance_cost: "距离便利度",
                budget_match: "预算匹配",
                rating_quality: "评分质量",
                availability_confidence: "营业可信度",
                novelty: "新鲜度",
                data_completeness: "数据完整度",
                total: "综合分",
              }[key] ?? key}
            </span>
            <span>{value.toFixed(1)}</span>
          </div>
        ))}
      </details>
      <div className="card-actions">
        {navigation ? (
          <Button variant="outline" asChild>
            <a href={navigation} target="_blank" rel="noopener noreferrer">在高德查看</a>
          </Button>
        ) : <Button variant="outline" disabled>地点暂无数据</Button>}
        <Button disabled={busy} onClick={onChoose}>
          选这家
        </Button>
      </div>
      {onExclude && (
        <button className="text-button" disabled={busy} onClick={onExclude}>
          这家不考虑
        </button>
      )}
      <p className="data-source">
        来源：高德地图 ·{" "}
        {new Date(place.dataUpdatedAt).toLocaleTimeString("zh-CN", {
          timeZone: "Asia/Shanghai",
          hour: "2-digit",
          minute: "2-digit",
        })}{" "}
        更新
      </p>
    </article>
  );
}
