import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, LocateFixed, Search, MapPin } from "lucide-react";
import { FoodMap } from "../components/map";
import { Button } from "../components/ui/button";
import { locate } from "../lib/amap";
import { request } from "../lib/api";
import { useDraft } from "../lib/store";
import type { Origin } from "../lib/schemas";
export function Location() {
  const navigate = useNavigate(),
    draft = useDraft(),
    [selected, setSelected] = useState<Origin | null>(draft.origin),
    [keywords, setKeywords] = useState(""),
    [tips, setTips] = useState<Origin[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    sequence = useRef(0);
  useEffect(() => {
    return () => { sequence.current += 1; };
  }, []);
  useEffect(() => {
    if (keywords.trim().length < 2) {
      setTips([]);
      return;
    }
    const abort = new AbortController();
    const timer = setTimeout(() => {
      request<Origin[]>(
        "/location-suggestions?query=" + encodeURIComponent(keywords),
        undefined,
        "GET",
        undefined,
        abort.signal,
      )
        .then(setTips)
        .catch((e) => {
          if (!abort.signal.aborted) setError(e.message);
        });
    }, 350);
    return () => {
      clearTimeout(timer);
      abort.abort();
    };
  }, [keywords]);
  const pick = async (point: Omit<Origin, "address">) => {
    const seq = ++sequence.current;
    setBusy(true);
    setSelected(null);
    setError("");
    try {
      const query = new URLSearchParams({
        latitude: String(point.latitude),
        longitude: String(point.longitude),
      });
      const origin = await request<Origin>(`/resolved-locations?${query}`);
      if (seq === sequence.current) setSelected(origin);
    } catch (e) {
      if (seq === sequence.current)
        setError(e instanceof Error ? e.message : "地址解析失败");
    } finally {
      if (seq === sequence.current) setBusy(false);
    }
  };
  const gps = async () => {
    const seq = ++sequence.current;
    setBusy(true);
    setError("");
    try {
      const point = await locate();
      if (seq === sequence.current) await pick(point);
    } catch (e) {
      if (seq === sequence.current) {
        setError(e instanceof Error ? e.message : "定位失败");
        setBusy(false);
      }
    }
  };
  return (
    <>
      <header className="compact-heading">
        <button aria-label="返回首页" onClick={() => navigate("/")}>
          <ArrowLeft />
        </button>
        <h1>选择出发地点</h1>
      </header>
      <div className="search-row">
        <label>
          <Search size={18} />
          <input
            aria-label="搜索地址"
            placeholder="搜索地址"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
          />
        </label>
        <Button variant="outline" disabled={busy} onClick={gps}>
          <LocateFixed size={17} />
          定位
        </Button>
      </div>
      {tips.length > 0 && (
        <div className="address-tips">
          {tips.map((tip, i) => (
            <button
              key={i}
              onClick={() => {
                setTips([]);
                setKeywords("");
                void pick(tip);
              }}
            >
              <MapPin size={16} />
              {tip.address}
            </button>
          ))}
        </div>
      )}
      <FoodMap origin={selected} onPick={pick} />
      <div className="selected-address">
        <MapPin size={18} />
        <span>
          {busy
            ? "正在确认地址…"
            : selected?.address || "搜索地址或点击地图，选择出发位置"}
        </span>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <Button
        className="primary-full"
        disabled={!selected || busy}
        onClick={() => {
          draft.setOrigin(selected);
          navigate("/");
        }}
      >
        使用这个位置
      </Button>
      <p className="footnote">仅在你确认后用于推荐，不持续追踪位置。</p>
    </>
  );
}
