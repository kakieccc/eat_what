import { useEffect, lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import {
  BrowserRouter,
  Navigate,
  Link,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  House,
  Clock as HistoryIcon,
  Heart,
} from "lucide-react";
import { Home, Profile } from "./pages/home";
import { AuthPage } from "./pages/auth";
import { Button } from "./components/ui/button";
import { BackgroundActivity } from "./components/background-activity";
import { AuthProvider, useAuth } from "./lib/auth";
const Location = lazy(() =>
  import("./pages/location").then((m) => ({ default: m.Location })),
);
const Discover = lazy(() =>
  import("./pages/discover").then((m) => ({ default: m.Discover })),
);
const History = lazy(() =>
  import("./pages/history").then((m) => ({ default: m.History })),
);
const Detail = lazy(() =>
  import("./pages/history").then((m) => ({ default: m.Detail })),
);
import { watchRecommendations } from "./lib/recommendations";
import { configError } from "./lib/api";
import "./styles.css";
const client = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30000, retry: 1, refetchOnWindowFocus: false },
  },
});
function RequireAuth() {
  const { state } = useAuth();
  const location = useLocation();
  return state === "authenticated"
    ? <Outlet />
    : <Navigate to="/login" replace state={{ from: location.pathname + location.search + location.hash }} />;
}
function App() {
  const { pathname } = useLocation();
  const auth = useAuth();
  const anonymous = pathname === "/login" || pathname === "/register";
  const homeSection = ["/", "/map", "/discover"].includes(pathname) || pathname.startsWith("/decision-runs/");
  useEffect(() => watchRecommendations(client), []);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return (
    <div className={`app-shell${anonymous ? " auth-shell" : ""}`}>
      {configError && (
        <aside role="alert" className="configuration-notice">
          {configError}
        </aside>
      )}
      {auth.state === "authenticated" && !configError && <BackgroundActivity />}
      <main>
        {configError ? null : auth.state === "loading" ? (
          <p role="status">正在检查登录状态…</p>
        ) : (
          <Suspense fallback={<p role="status">正在打开页面…</p>}>
            {auth.state === "error" && <div role="alert" className="error">
              <p>500 Error：无法检查登录状态，请确认网络和后端服务。</p>
              <Button variant="outline" onClick={() => void auth.retrySession()}>重试</Button>
            </div>}
            <Routes>
              <Route path="/login" element={<AuthPage mode="login" />} />
              <Route path="/register" element={<AuthPage mode="register" />} />
              <Route element={<RequireAuth />}>
                <Route path="/" element={<Home />} />
                <Route path="/map" element={<Location />} />
                <Route path="/discover" element={<Discover />} />
                <Route path="/decision-runs/:runId" element={<Detail />} />
                <Route path="/history" element={<History />} />
                <Route path="/profile" element={<Profile />} />
                <Route
                  path="*"
                  element={<div className="empty">
                    <h1>这一页走丢了</h1>
                    <NavLink to="/">返回首页</NavLink>
                  </div>}
                />
              </Route>
            </Routes>
          </Suspense>
        )}
      </main>
      {auth.state === "authenticated" && !configError && <nav className="bottom-nav" aria-label="主导航">
        <Link to="/" className={homeSection ? "active" : undefined} aria-current={homeSection ? "page" : undefined}>
          <House size={21} />
          <span>首页</span>
        </Link>
        <NavLink to="/history">
          <HistoryIcon size={21} />
          <span>历史</span>
        </NavLink>
        <NavLink to="/profile">
          <Heart size={21} />
          <span>偏好</span>
        </NavLink>
      </nav>}
    </div>
  );
}
ReactDOM.createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={client}>
    <BrowserRouter>
      <AuthProvider><App /></AuthProvider>
    </BrowserRouter>
  </QueryClientProvider>,
);
