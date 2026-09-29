import { useEffect, useRef, useState } from "react";
import { MapPin, RotateCcw } from "lucide-react";
import { loadMap, type MapInstance } from "../lib/amap";
import type { Origin, Place } from "../lib/schemas";
interface Props {
  origin: Origin | null;
  places?: Place[];
  selected?: string | null;
  route?: boolean;
  onSelect?: (id: string) => void;
  onPick?: (point: Omit<Origin, "address">) => void;
}
const empty: Place[] = [];
export function FoodMap({
  origin,
  places = empty,
  selected,
  route = false,
  onSelect,
  onPick,
}: Props) {
  const element = useRef<HTMLDivElement>(null),
    instance = useRef<MapInstance | null>(null);
  const [ready, setReady] = useState(false),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  const handlers = useRef({ onSelect, onPick });
  handlers.current = { onSelect, onPick };
  useEffect(() => {
    let active = true;
    setError("");
    setReady(false);
    loadMap()
      .then((amap) => {
        if (!active || !element.current) return;
        const map = new amap.Map(element.current, { zoom: 15, viewMode: "2D" });
        instance.current = map;
        map.on("click", (e) =>
          handlers.current.onPick?.({
            latitude: e.lnglat.getLat(),
            longitude: e.lnglat.getLng(),
          }),
        );
        setReady(true);
      })
      .catch(
        (e) =>
          active && setError(e instanceof Error ? e.message : "地图加载失败"),
      );
    return () => {
      active = false;
      instance.current?.destroy();
      instance.current = null;
    };
  }, [retry]);
  useEffect(() => {
    if (!ready || !instance.current) return;
    const map = instance.current;
    let objects: unknown[] = [];
    let active = true;
    loadMap()
      .then((amap) => {
        if (!active) return;
        if (origin) {
          objects.push(
            new amap.Marker({
              position: [origin.longitude, origin.latitude],
              title: "出发位置",
            }),
          );
          map.setCenter([origin.longitude, origin.latitude]);
        }
        for (const place of places) {
          const marker = new amap.Marker({
            position: [place.location.longitude, place.location.latitude],
            title: place.name,
            label: { content: String(place.rank), direction: "top" },
          });
          marker.on("click", () => handlers.current.onSelect?.(place.id));
          objects.push(marker);
        }
        const chosen = places.find((p) => p.id === selected);
        if (chosen && route && chosen.route)
          objects.push(
            new amap.Polyline({
              path: chosen.route.polyline.map((p) => [p.longitude, p.latitude]),
              strokeColor: "#bf5437",
              strokeWeight: 6,
              showDir: true,
            }),
          );
        map.add(objects);
        if (places.length) map.setFitView();
        if (chosen && !route)
          map.setCenter([chosen.location.longitude, chosen.location.latitude]);
      })
      .catch(() => setError("地图加载失败"));
    return () => {
      active = false;
      if (objects.length) map.remove(objects);
      objects = [];
    };
  }, [origin, places, selected, route, ready]);
  return (
    <div className="map-wrap">
      <div ref={element} className="map-canvas" aria-label="高德地图" />
      {!ready && (
        <div className="map-message">
          <MapPin size={36} />
          <p>{error || "正在加载高德地图"}</p>
          {error && (
            <button type="button" onClick={() => setRetry((v) => v + 1)}>
              <RotateCcw size={16} />
              重试
            </button>
          )}
        </div>
      )}
    </div>
  );
}
