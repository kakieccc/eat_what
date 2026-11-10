import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, LocateFixed, Search, MapPin } from "lucide-react";
import { FoodMap } from "../components/map";
import { Button } from "../components/ui/button";
import { DesktopPageHeader } from "../components/desktop-page-header";
import { useDesktop } from "../lib/use-desktop";
import { locate, resolveLocation } from "../lib/amap";
import { request } from "../lib/api";
import { useDraft } from "../lib/store";
import { originSchema, type Origin } from "../lib/schemas";
export function Location() {
  const desktop = useDesktop();
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
      request(
        "/location-suggestions?query=" + encodeURIComponent(keywords),
        undefined,
        "GET",
        undefined,
        abort.signal,
        originSchema.array(),
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
    // Only the latest map pick or GPS result may replace the selected address.
    const seq = ++sequence.current;
    setBusy(true);
    setSelected(null);
    setError("");
    try {
      const origin = await resolveLocation(point);
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
  const searchControls = (
    <>
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
    </>
  );
  const selection = (
    <>
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
  const map = <FoodMap origin={selected} onPick={pick} />;
  return (
    <section className="location-page">
      {desktop ? <DesktopPageHeader title="选择出发地点" description="搜索地址或在地图上选点，确认这一餐从哪里出发。">
        <Button variant="outline" onClick={() => navigate("/")}><ArrowLeft data-icon="inline-start" />返回选餐</Button>
      </DesktopPageHeader> : <header className="compact-heading">
        <button aria-label="返回首页" onClick={() => navigate("/")}><ArrowLeft /></button>
        <h1>选择出发地点</h1>
      </header>}
      {desktop ? <div className="desktop-location-layout">
        <div className="desktop-location-map">{map}</div>
        <aside className="desktop-location-controls">
          <h2>从哪里出发？</h2>
          {searchControls}
          {selection}
        </aside>
      </div> : <>{searchControls}{map}{selection}</>}
    </section>
  );
}
