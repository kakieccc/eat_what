import { useEffect, useRef, useState } from "react";
import { MapPin, Minus, Plus, RotateCcw } from "lucide-react";
import { loadMap, type MapInstance } from "../lib/amap";
import type { Origin, Place } from "../lib/schemas";
import { formatDistance } from "../lib/utils";
interface Props {
  origin: Origin | null;
  places?: Place[];
  selected?: string | null;
  radiusMeters?: number;
  onSelect?: (id: string) => void;
  onPick?: (point: Omit<Origin, "address">) => void;
}
const empty: Place[] = [];
export function FoodMap({
  origin,
  places = empty,
  selected,
  radiusMeters,
  onSelect,
  onPick,
}: Props) {
  const element = useRef<HTMLDivElement>(null),
    instance = useRef<MapInstance | null>(null);
  const [ready, setReady] = useState(false),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  // Map listeners need current callbacks without recreating the SDK map on every render.
  const handlers = useRef({ onSelect, onPick, selected });
  handlers.current = { onSelect, onPick, selected };
  useEffect(() => {
    let active = true;
    setError("");
    setReady(false);
    loadMap()
      .then((amap) => {
        if (!active || !element.current) return;
        const map = new amap.Map(element.current, {
          zoom: 15,
          viewMode: "2D",
          animateEnable: false,
          mapStyle: "amap://styles/fresh",
        });
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
        () => active && setError("地图加载失败，请稍后重试"),
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
          if (radiusMeters) objects.push(new amap.Circle({
            center: [origin.longitude, origin.latitude], radius: radiusMeters,
            strokeColor: "#a7be63", strokeWeight: 1, strokeStyle: "dashed",
            fillColor: "#e5ecad", fillOpacity: 0.2,
          }));
          const originContent = document.createElement("div");
          originContent.className = "map-origin";
          const originLabel = document.createElement("span");
          originLabel.textContent = "出发地";
          originContent.append(originLabel);
          objects.push(
            new amap.Marker({
              position: [origin.longitude, origin.latitude],
              title: "出发位置",
              content: originContent,
              anchor: "center",
            }),
          );
        }
        for (const place of places) {
          const content = document.createElement("button");
          content.type = "button";
          content.className = "map-food-pin";
          content.dataset.placeId = place.id;
          const cuisine = place.cuisineTypes.join(" ") || place.categoryName;
          content.dataset.food = /饺|馄饨|包子/.test(cuisine) ? "dumplings" : /面|粉/.test(cuisine) ? "noodles" : "rice";
          content.setAttribute("aria-label", `推荐第 ${place.rank} 家：${place.name}`);
          content.setAttribute("aria-pressed", String(place.id === handlers.current.selected));
          const rank = document.createElement("span");
          rank.className = "map-pin-rank";
          rank.textContent = String(place.rank);
          content.append(rank);
          content.addEventListener("click", (event) => {
            event.stopPropagation();
            handlers.current.onSelect?.(place.id);
          });
          const marker = new amap.Marker({
            position: [place.location.longitude, place.location.latitude],
            title: place.name,
            content,
            anchor: "bottom-center",
            offset: [0, 10],
            zIndex: 100,
          });
          objects.push(marker);
        }
        const chosen = places.find((p) => p.id === handlers.current.selected);
        map.add(objects);
        if (chosen)
          map.setCenter([chosen.location.longitude, chosen.location.latitude], true);
        else if (places.length) map.setFitView(undefined, true);
        else if (origin) map.setCenter([origin.longitude, origin.latitude], true);
      })
      .catch(() => {
        if (active) setError("地图加载失败，请稍后重试");
      });
    return () => {
      active = false;
      // The map's own effect destroys it before overlay cleanup on unmount.
      if (objects.length && instance.current === map) map.remove(objects);
      objects = [];
    };
  }, [origin, places, radiusMeters, ready]);
  useEffect(() => {
    if (!ready || !instance.current) return;
    element.current?.querySelectorAll<HTMLButtonElement>(".map-food-pin").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.placeId === selected));
    });
    const chosen = places.find((place) => place.id === selected);
    if (chosen) instance.current.setCenter([chosen.location.longitude, chosen.location.latitude], true);
  }, [selected, places, ready]);
  return (
    <div className="map-wrap">
      <div ref={element} className="map-canvas" aria-label="高德地图" />
      {ready && !error && <>
        {radiusMeters && <span className="map-radius">{formatDistance(radiusMeters)}</span>}
        <div className="map-zoom" aria-label="地图缩放">
          <button type="button" aria-label="放大地图" onClick={() => instance.current?.zoomIn()}><Plus size={20} aria-hidden="true" /></button>
          <button type="button" aria-label="缩小地图" onClick={() => instance.current?.zoomOut()}><Minus size={20} aria-hidden="true" /></button>
        </div>
      </>}
      {(!ready || error) && (
        <div className="map-message" role={error ? "alert" : "status"}>
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
