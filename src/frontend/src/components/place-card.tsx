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
    <article className={cn("place-card", { selected })} onFocus={onSelect}>
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
      {place.openingHoursText && (
        <p className="muted">营业时间：{place.openingHoursText}</p>
      )}
      {place.warnings?.map((w) => (
        <p className="warning-text" key={w}>
          {w}
        </p>
      ))}
      <div className="card-actions">
        {navigation ? (
          <Button variant="outline" asChild>
            <a href={navigation} target="_blank" rel="noopener noreferrer">
              在高德查看
            </a>
          </Button>
        ) : (
          <Button variant="outline" disabled>
            地点暂无数据
          </Button>
        )}
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
