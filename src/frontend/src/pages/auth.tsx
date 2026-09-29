import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Button } from "../components/ui/button";
import { useAuth } from "../lib/auth";

function returnPath(state: unknown): string {
  const from = state && typeof state === "object" && "from" in state
    ? (state as { from: unknown }).from : null;
  return typeof from === "string" && from.startsWith("/") && !from.startsWith("//")
    && !/^\/(login|register)([/?#]|$)/.test(from) ? from : "/";
}

export function AuthPage({ mode }: { mode: "login" | "register" }) {
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
  return <section className="auth-page">
    <section className="auth-card">
      <h1>{mode === "register" ? "创建账号" : "欢迎回来"}</h1>
      <p>登录后，开始寻找今天这一餐。</p>
      <form onSubmit={submit}>
        <label className="field-label">用户名
          <input required minLength={3} maxLength={32} pattern="[A-Za-z0-9_]+"
            autoComplete="username" value={username}
            onChange={(event) => setUsername(event.target.value)} />
        </label>
        {mode === "register" && <label className="field-label">昵称
          <input required maxLength={40} autoComplete="nickname" value={displayName}
            onChange={(event) => setDisplayName(event.target.value)} />
        </label>}
        <label className="field-label">密码
          <input required type="password" minLength={mode === "register" ? 8 : undefined}
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
