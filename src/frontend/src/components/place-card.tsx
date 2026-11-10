import { ArrowUpRight, ChevronDown } from "lucide-react";
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
  return (
    <article className={cn("place-card", { selected, "first-place": place.rank === 1 })} onFocus={onSelect}>
      <button className="place-title" onClick={onSelect}>
        <span className="rank">{place.rank}</span>
        <h2>{place.name}</h2>
      </button>
      <PlaceFacts place={place} />
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
        {onExclude && <button className="text-button" disabled={busy} onClick={onExclude}>这家不考虑</button>}
      </details>
    </article>
  );
}
