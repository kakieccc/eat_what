import { useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { MapPin, ChevronRight } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PreferencesForm } from "../components/preferences-form";
import { Button } from "../components/ui/button";
import { useDraft } from "../lib/store";
import { useAuth } from "../lib/auth";
import { configError, request } from "../lib/api";
import {
  preferencesSnapshotSchema,
  type Preferences,
  defaults,
  runSchema,
  toDecisionRequest,
  storedPreferencesSchema,
} from "../lib/schemas";
export function Home() {
  const draft = useDraft(),
    navigate = useNavigate();
  const saved = useQuery({
    queryKey: ["preferences"],
    queryFn: () =>
      request(
        "/preferences",
        undefined,
        "GET",
        undefined,
        undefined,
        storedPreferencesSchema,
      ).then((p) => preferencesSnapshotSchema.parse({ ...defaults, ...p })),
    enabled: !draft.hasDraft && !configError,
    retry: false,
  });
  const client = useQueryClient();
  const submission = useRef<{ body: string; key: string } | null>(null);
  const submit = async (preferences: Preferences) => {
    draft.setPreferences(preferences);
    if (!draft.origin) {
      navigate("/map");
      return;
    }
    const body = toDecisionRequest(preferences, draft.origin);
    const serialized = JSON.stringify(body);
    if (submission.current?.body !== serialized)
      submission.current = { body: serialized, key: crypto.randomUUID() };
    const run = await request(
      "/decision-runs",
      body,
      "POST",
      submission.current.key,
      undefined,
      runSchema,
    );
    submission.current = null;
    client.setQueryData(["run", run.decisionRunId], run);
    draft.setRunId(run.decisionRunId);
    navigate("/discover");
  };
  return (
    <>
      <header className="page-heading">
        <h1>今天，吃点什么？</h1>
        <p>从附近出发，找到合心意的一餐。</p>
      </header>
      <Link to="/map" className="location-link">
        <MapPin size={20} />
        <span>{draft.origin?.address || "先选一个出发地点"}</span>
        <ChevronRight size={18} />
      </Link>
      {!draft.hasDraft && !configError && saved.isPending ? (
        <p>正在读取偏好…</p>
      ) : (
        <PreferencesForm
          initial={
            draft.hasDraft
              ? draft.preferences
              : (saved.data ?? draft.preferences)
          }
          onSubmit={submit}
          label="帮我选一家"
        />
      )}
      <p className="footnote">真实地点 · 按范围寻找 · 三个合心意的选择</p>
    </>
  );
}
export function Profile() {
  const auth = useAuth(),
    navigate = useNavigate();
  const query = useQuery({
    queryKey: ["preferences"],
    queryFn: () =>
      request(
        "/preferences",
        undefined,
        "GET",
        undefined,
        undefined,
        storedPreferencesSchema,
      ).then((p) => preferencesSnapshotSchema.parse({ ...defaults, ...p })),
    retry: false,
  });
  const client = useQueryClient(),
    draft = useDraft(),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const logout = async () => {
    setLogoutBusy(true);
    setLogoutError("");
    try {
      await auth.logout();
      navigate("/login", { replace: true });
    } catch (e) {
      setLogoutError(e instanceof Error ? e.message : "退出失败");
    } finally {
      setLogoutBusy(false);
    }
  };
  const save = async (p: Preferences) => {
    setBusy(true);
    setNotice("");
    try {
      const saved = await request(
        "/preferences",
        storedPreferencesSchema.parse(p),
        "PUT",
        undefined,
        undefined,
        storedPreferencesSchema,
      ).then((p) => preferencesSnapshotSchema.parse({ ...defaults, ...p }));
      client.setQueryData(["preferences"], saved);
      draft.setPreferences(saved);
      setNotice("偏好已保存，下次选餐时会使用这些条件。");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <header className="page-heading">
        <h1>你的用餐偏好</h1>
        <p>把常用条件留给下一餐。</p>
      </header>
      {query.isPending ? (
        <p>正在读取偏好…</p>
      ) : query.isError ? (
        <div role="alert" className="error">
          {query.error.message}
          <button onClick={() => query.refetch()}>重试</button>
        </div>
      ) : (
        <PreferencesForm
          initial={query.data}
          onSubmit={save}
          personal
          label="保存偏好"
          busy={busy}
        />
      )}
      <p role="status">{notice}</p>
      <section className="account-panel" aria-label="当前账号">
        <div>
          <strong>{auth.user?.displayName}</strong>
          <p>@{auth.user?.username}</p>
        </div>
        <Button
          variant="outline"
          disabled={logoutBusy}
          onClick={() => void logout()}
        >
          {logoutBusy ? "正在退出…" : "退出登录"}
        </Button>
      </section>
      {logoutError && (
        <p role="alert" className="error">
          {logoutError}
        </p>
      )}
    </>
  );
}
