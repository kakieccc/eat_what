import { CircleDollarSign, Clock, MapPin, Star, Utensils } from "lucide-react";
import type { Place } from "../lib/schemas";
import { cn, formatDistance } from "../lib/utils";

export function PlaceFacts({ place, compact = false }: { place: Place; compact?: boolean }) {
  return (
    <div className={cn("place-facts", { compact })}>
      <div className="place-meta">
        <p>
          <Utensils size={16} aria-hidden="true" />
          <span className="sr-only">分类：</span>
          <span>{place.cuisineTypes.join(" · ") || place.categoryName || "暂无信息"}</span>
        </p>
        <p>
          <Clock size={16} aria-hidden="true" />
          <span className="place-meta-label">营业时间</span>
          <span>{place.openingHoursText || "暂无信息"}</span>
        </p>
      </div>
      <dl className="place-metrics">
        <div>
          <dt>{compact ? <><MapPin size={15} aria-hidden="true" /><span className="sr-only">直线距离</span></> : "直线距离"}</dt>
          <dd>{formatDistance(place.straightLineDistanceMeters)}</dd>
        </div>
        <div>
          <dt>{compact ? <><CircleDollarSign size={15} aria-hidden="true" /><span className="sr-only">人均</span></> : "人均"}</dt>
          <dd data-missing={place.averageCost === null || undefined}>
            {place.averageCost === null ? "暂无信息" : <>{`¥${place.averageCost}`}{compact && <span className="metric-unit"> / 人</span>}</>}
          </dd>
        </div>
        <div>
          <dt><Star size={16} aria-hidden="true" /><span className={compact ? "sr-only" : undefined}>评分</span></dt>
          <dd data-missing={place.rating === null || undefined}>{place.rating ?? "暂无信息"}</dd>
        </div>
      </dl>
    </div>
  );
}
