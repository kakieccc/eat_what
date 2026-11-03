import { MapPin, Star, ArrowUpRight, ChevronDown } from "lucide-react";
import type { Place } from "../lib/schemas";
import { cn, formatDistance } from "../lib/utils";
import { Button } from "./ui/button";
import { BrandMark } from "./brand";
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
  const navigation = place.navigationUrl;
  return (
    <article className={cn("place-card", { selected, "first-place": place.rank === 1 })} onFocus={onSelect}>
      <button className="place-title" onClick={onSelect}>
        <span className="rank"><BrandMark /><span>{place.rank}</span></span>
        <h2>{place.name}</h2>
      </button>
      <p className="muted">{place.cuisineTypes.join(" · ")}</p>
      <div className="place-stats">
        <span>
          <MapPin size={16} />
          直线 {formatDistance(place.straightLineDistanceMeters)}
        </span>
        <span>
          {place.averageCost !== null
            ? <>¥<strong>{place.averageCost}</strong><small>/ 人</small></>
            : "人均暂无数据"}
        </span>
        <span>
          <Star size={15} fill="currentColor" />
          <strong>{place.rating ?? "暂无数据"}</strong>
        </span>
      </div>
      <p className="reason">{place.reason}</p>
      {place.warnings.map((w) => (
        <p className="warning-text" key={w}>
          {w}
        </p>
      ))}
      <div className="card-actions">
        <Button variant={place.rank === 1 ? "default" : "secondary"} disabled={busy} onClick={onChoose}>
          选这家
        </Button>
        {navigation ? (
          <Button variant="outline" asChild>
            <a href={navigation} target="_blank" rel="noopener noreferrer">
              <ArrowUpRight data-icon="inline-start" />
              在高德查看
            </a>
          </Button>
        ) : (
          <Button variant="outline" disabled>
            地点暂无数据
          </Button>
        )}
      </div>
      <details className="place-options">
        <summary>
          <span className="data-source">
            来源：高德地图 · {new Date(place.dataUpdatedAt).toLocaleTimeString("zh-CN", {
              timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit",
            })} 更新
          </span>
          <span>更多 <ChevronDown size={14} /></span>
        </summary>
        {place.openingHoursText && <p className="muted">营业时间：{place.openingHoursText}</p>}
        {onExclude && <button className="text-button" disabled={busy} onClick={onExclude}>这家不考虑</button>}
      </details>
    </article>
  );
}
