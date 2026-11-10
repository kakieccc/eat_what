import { useEffect, lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import {
  BrowserRouter,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Home, Profile } from "./pages/home";
import { AuthPage } from "./pages/auth";
import { ServiceError } from "./pages/error";
import { DesktopNavigation, MobileNavigation } from "./components/app-navigation";
import { useBackgroundActivity } from "./components/background-activity";
import { AuthProvider, useAuth } from "./lib/auth";
import { useDefaultLocation } from "./lib/use-default-location";
import { useDesktop } from "./lib/use-desktop";
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
import { configError, setServiceErrorHandler } from "./lib/api";
import { cn } from "./lib/utils";
import "./styles.css";
import "./desktop.css";
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
  const location = useLocation();
  const { pathname } = location;
  const navigate = useNavigate();
  const auth = useAuth();
  const desktop = useDesktop();
  useDefaultLocation(auth.state === "authenticated" ? auth.user?.id : undefined);
  const anonymous = pathname === "/login" || pathname === "/register";
  const errorPage = pathname === "/error";
  const showNavigation = auth.state === "authenticated" && !configError && !errorPage;
  const activity = useBackgroundActivity(showNavigation);
  useEffect(() => watchRecommendations(client), []);
  useEffect(() => {
    setServiceErrorHandler(() => {
      if (location.pathname !== "/error") navigate("/error", {
        replace: true, state: { from: location.pathname + location.search + location.hash },
      });
    });
    return () => setServiceErrorHandler(null);
  }, [location, navigate]);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return (
    <div className={cn(desktop ? "desktop-shell" : "app-shell", {
      "auth-shell": anonymous, "error-shell": errorPage, "public-layout": !showNavigation,
    })}>
      {showNavigation && desktop && <DesktopNavigation />}
      {configError && !errorPage && (
        <aside role="alert" className="configuration-notice">
          {configError}
        </aside>
      )}
      {pathname !== "/discover" && activity}
      <main>
        {configError && !errorPage ? null : auth.state === "error" && !errorPage ? (
          <Navigate to="/error" replace state={{ from: location.pathname + location.search + location.hash }} />
        ) : auth.state === "loading" && !errorPage ? (
          <p role="status">正在检查登录状态…</p>
        ) : (
          <Suspense fallback={<p role="status">正在打开页面…</p>}>
            <Routes>
              <Route path="/error" element={<ServiceError />} />
              <Route path="/login" element={<AuthPage mode="login" />} />
              <Route path="/register" element={<AuthPage mode="register" />} />
              <Route element={<RequireAuth />}>
                <Route path="/" element={<Home />} />
                <Route path="/map" element={<Location />} />
                <Route path="/discover" element={<Discover progress={activity} />} />
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
      {showNavigation && !desktop && <MobileNavigation />}
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
