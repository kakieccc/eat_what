import { useId, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  ChevronDown,
  Clock,
  Utensils,
} from "lucide-react";
import type { Place } from "../lib/schemas";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";
import { PlaceFacts } from "./place-facts";
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
  const detailsId = useId();
  const [failedPhoto, setFailedPhoto] = useState<string | null>(null);
  const photo = place.photos[0];
  return (
    <article
      className={cn("place-card", {
        selected,
        "first-place": place.rank === 1,
      })}
    >
      <div className="place-photo">
        {photo && failedPhoto !== photo ? (
          <img
            src={photo}
            alt={`${place.name}的餐厅照片`}
            loading="lazy"
            onError={() => setFailedPhoto(photo)}
          />
        ) : (
          <Utensils size={28} aria-hidden="true" />
        )}
        <span className="rank" aria-label={`推荐第 ${place.rank} 家`}>
          {place.rank}
        </span>
      </div>
      <div className="place-content">
        <h2>
          <button
            className="place-title"
            onClick={onSelect}
            aria-expanded={selected}
            aria-controls={detailsId}
          >
            <span>{place.name}</span>
            <ChevronDown size={20} aria-hidden="true" />
          </button>
        </h2>
        <PlaceFacts place={place} compact />
        {place.warnings.map((w) => (
          <p className="warning-text" key={w}>
            {w}
          </p>
        ))}
        <div
          id={detailsId}
          className="place-expansion"
          inert={!selected}
          aria-hidden={!selected}
        >
          <div>
            {place.reason && <p className="place-reason">{place.reason}</p>}
            <div className="card-actions">
              <Button disabled={busy} onClick={onChoose}>
                选这家
                <ArrowRight data-icon="inline-end" />
              </Button>
            </div>
            <details className="place-options">
              <summary>
                营业与来源
                <ChevronDown size={14} aria-hidden="true" />
              </summary>
              <p className="opening-hours">
                <Clock size={14} aria-hidden="true" />
                {place.openingHoursText || "营业时间暂无信息"}
              </p>
              <p className="data-source">
                来源：高德地图 ·{" "}
                {new Date(place.dataUpdatedAt).toLocaleTimeString("zh-CN", {
                  timeZone: "Asia/Shanghai",
                  hour: "2-digit",
                  minute: "2-digit",
                })}{" "}
                更新
              </p>
              {navigation ? (
                <a
                  className="text-button place-navigation"
                  href={navigation}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ArrowUpRight size={15} aria-hidden="true" />
                  在高德查看
                </a>
              ) : (
                <p className="muted">地点暂无数据</p>
              )}
              {onExclude && (
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={onExclude}
                >
                  这家不考虑
                </button>
              )}
            </details>
          </div>
        </div>
      </div>
    </article>
  );
}
