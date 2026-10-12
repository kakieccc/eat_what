import AMapLoader from "@amap/amap-jsapi-loader";
import { config, configError } from "./api";
import type { Origin } from "./schemas";
export interface LngLat {
  getLat(): number;
  getLng(): number;
}
export interface MapInstance {
  destroy(): void;
  on(event: string, fn: (event: { lnglat: LngLat }) => void): void;
  add(objects: unknown[]): void;
  remove(objects: unknown[]): void;
  setCenter(point: [number, number]): void;
  setFitView(): void;
}
export interface MarkerInstance {
  on(event: string, fn: () => void): void;
}
export interface AmapAPI {
  Map: new (element: HTMLElement, options: object) => MapInstance;
  Marker: new (options: object) => MarkerInstance;
  convertFrom(
    point: [number, number],
    type: string,
    callback: (status: string, result: { locations: LngLat[] }) => void,
  ): void;
}
let promise: Promise<AmapAPI> | null = null;
export function loadMap(): Promise<AmapAPI> {
  if (!config.success)
    return Promise.reject(new Error(configError ?? "地图配置不完整"));
  if (!promise) {
    (window as Window & { _AMapSecurityConfig?: object })._AMapSecurityConfig =
      { securityJsCode: config.data.VITE_AMAP_SECURITY_CODE };
    promise = (
      AMapLoader.load({
        key: config.data.VITE_AMAP_JS_KEY,
        version: "2.0",
      }) as Promise<AmapAPI>
    ).catch((e) => {
      promise = null;
      throw e;
    });
  }
  return promise;
}
export async function locate(): Promise<Omit<Origin, "address">> {
  const gps = await new Promise<GeolocationPosition>((resolve, reject) =>
    navigator.geolocation.getCurrentPosition(
      resolve,
      () => reject(new Error("定位失败或权限未授权，请搜索地址或在地图上选点")),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    ),
  );
  const amap = await loadMap();
  return new Promise((resolve, reject) =>
    amap.convertFrom(
      [gps.coords.longitude, gps.coords.latitude],
      "gps",
      (status, result) => {
        if (status !== "complete" || !result.locations?.length)
          reject(new Error("坐标转换失败，请在地图上选点"));
        else
          resolve({
            latitude: result.locations[0].getLat(),
            longitude: result.locations[0].getLng(),
          });
      },
    ),
  );
}
