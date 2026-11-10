import { Clock, Star, Utensils } from "lucide-react";
import type { Place } from "../lib/schemas";
import { formatDistance } from "../lib/utils";

export function PlaceFacts({ place }: { place: Place }) {
  return (
    <div className="place-facts">
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
          <dt>直线距离</dt>
          <dd>{formatDistance(place.straightLineDistanceMeters)}</dd>
        </div>
        <div>
          <dt>人均</dt>
          <dd data-missing={place.averageCost === null || undefined}>
            {place.averageCost === null ? "暂无信息" : `¥${place.averageCost}`}
          </dd>
        </div>
        <div>
          <dt><Star size={16} aria-hidden="true" />评分</dt>
          <dd data-missing={place.rating === null || undefined}>{place.rating ?? "暂无信息"}</dd>
        </div>
      </dl>
    </div>
  );
}
