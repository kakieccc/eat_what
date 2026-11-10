import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Button } from "../components/ui/button";
import { useAuth } from "../lib/auth";
import { Brand, PageHero } from "../components/brand";
import { useDesktop } from "../lib/use-desktop";
import { returnPath } from "../lib/utils";

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const desktop = useDesktop();
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const destination = returnPath(location.state);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (mode === "register" && !displayName.trim()) {
      setError("昵称不能为空");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (mode === "register") await auth.register(username, password, displayName);
      else await auth.login(username, password);
      navigate(destination, { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "操作失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  };
  if (auth.state === "authenticated")
    return <Navigate to={destination} replace />;
  return <section className={desktop ? "desktop-auth-page" : "auth-page"}>
    {desktop ? <aside className="desktop-auth-intro">
      <Brand />
      <div><h2>这一餐，<br />有个好选择。</h2><p>从附近出发，找到合心意的一家。</p></div>
    </aside> : <PageHero className="auth-hero">
      <Brand />
      <h1>{mode === "register" ? "创建账号" : "欢迎回来"}</h1>
    </PageHero>}
    <section className="auth-card">
      {desktop && <header><h1>{mode === "register" ? "创建账号" : "欢迎回来"}</h1><p>{mode === "register" ? "留下你的用餐偏好，下次选餐更轻松。" : "登录后，继续选择合心意的一餐。"}</p></header>}
      {mode === "login" && new URLSearchParams(location.search).get("passwordChanged") === "1" && (
        <p className="auth-notice" role="status">密码已修改，请使用新密码重新登录。</p>
      )}
      <form onSubmit={submit}>
        <label className="field-label">用户名
          <input required minLength={3} maxLength={32} pattern="[A-Za-z0-9_]+"
            placeholder={mode === "register" ? "3–32 位字母、数字或下划线" : "输入用户名"}
            autoComplete="username" value={username}
            onChange={(event) => setUsername(event.target.value)} />
        </label>
        {mode === "register" && <label className="field-label">昵称
          <input required maxLength={40} autoComplete="nickname" placeholder="怎么称呼你" value={displayName}
            onChange={(event) => setDisplayName(event.target.value)} />
        </label>}
        <label className="field-label">密码
          <input required type="password" placeholder={mode === "register" ? "至少 8 位字符" : "输入密码"} minLength={mode === "register" ? 8 : undefined}
            maxLength={128} autoComplete={mode === "register" ? "new-password" : "current-password"}
            value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <Button className="primary-full" disabled={busy} type="submit">
          {busy ? "请稍候…" : mode === "register" ? "注册并登录" : "登录"}
        </Button>
      </form>
      <p className="auth-switch">{mode === "register" ? "已有账号？" : "还没有账号？"}{" "}
        <Link to={mode === "register" ? "/login" : "/register"}
          state={{ from: destination }}>
          {mode === "register" ? "去登录" : "创建账号"}
        </Link>
      </p>
    </section>
  </section>;
}
