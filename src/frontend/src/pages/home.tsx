import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { MapPin, ChevronRight } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PreferencesForm } from "../components/preferences-form";
import { Button } from "../components/ui/button";
import { useDraft } from "../lib/store";
import { readRecommendation } from "../lib/recommendations";
import { useAuth } from "../lib/auth";
import { configError, request } from "../lib/api";
import {
  type Preferences,
  type Run,
  type AccountPreferences,
  type LearnableField,
  defaults,
  toDecisionRequest,
  accountPreferencesSchema,
  editedOverrides,
} from "../lib/schemas";

const readPreferences = () =>
  request(
    "/preferences",
    undefined,
    "GET",
    undefined,
    undefined,
    accountPreferencesSchema,
  );

export function Home() {
  const draft = useDraft(),
    navigate = useNavigate();
  const saved = useQuery({
    queryKey: ["preferences"],
    queryFn: readPreferences,
    enabled: !draft.hasDraft && !configError,
    retry: false,
  });
  useEffect(() => {
    if (
      !draft.hasDraft &&
      !saved.isFetching &&
      (saved.data || saved.isError || configError)
    ) {
      draft.initialize(
        { ...defaults, ...saved.data?.defaults },
        "defaults",
        saved.data?.revision ?? null,
      );
    }
  }, [draft, saved.data, saved.isError, saved.isFetching]);
  const client = useQueryClient();
  const runQuery = useQuery<Run>({
    queryKey: ["run", draft.runId],
    queryFn: ({ signal }) => readRecommendation(client, draft.runId!, signal),
    enabled: false,
  });
  const run = runQuery.data;
  const busy =
    draft.job?.status === "submitting" ||
    (!!draft.runId &&
      ((!run && !runQuery.isError) ||
        run?.status === "pending" ||
        run?.status === "running"));
  const submit = (preferences: Preferences) => {
    draft.setPreferences(preferences);
    if (!draft.origin) {
      navigate("/map");
      return;
    }
    if (!draft.prefill) throw new Error("请重新开始本次选餐");
    draft.enqueue("recommendation", "/decision-runs", {
      ...toDecisionRequest(preferences, draft.origin),
      prefillSnapshot: draft.prefill,
    });
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
      {saved.isError && (
        <p role="alert" className="error">
          500 Error：账户偏好读取失败，请检查本次条件。
        </p>
      )}
      {!draft.hasDraft ? (
        <p>正在读取偏好…</p>
      ) : (
        <PreferencesForm
          initial={draft.preferences}
          onSubmit={submit}
          onDraftChange={draft.setPreferences}
          busy={busy}
          label="帮我选一家"
        />
      )}
      <p className="footnote">真实地点 · 按范围寻找 · 三个合心意的选择</p>
    </>
  );
}

function PreferenceEditor({
  initial,
  onSaved,
}: {
  initial: AccountPreferences;
  onSaved: (value: AccountPreferences) => void;
}) {
  // Keep the editing baseline stable until an explicit save or reload.
  const [baseline] = useState(initial);
  const [automatic, setAutomatic] = useState<LearnableField[]>([]);
  const save = async (p: Preferences) => {
    const saved = await request(
      "/preferences",
      {
        revision: baseline.revision,
        overrides: editedOverrides(baseline, p, automatic),
      },
      "PUT",
      undefined,
      undefined,
      accountPreferencesSchema,
    );
    onSaved(saved);
  };
  return (
    <PreferencesForm
      initial={{ ...defaults, ...baseline.defaults }}
      onSubmit={save}
      personal
      label="保存偏好"
      memory={{
        sources: baseline.sources,
        overrides: baseline.overrides,
        automatic,
        onRestore: (key) =>
          setAutomatic((current) =>
            current.includes(key)
              ? current.filter((field) => field !== key)
              : [...current, key],
          ),
      }}
    />
  );
}

export function Profile() {
  const auth = useAuth(),
    navigate = useNavigate();
  const query = useQuery({
    queryKey: ["preferences"],
    queryFn: readPreferences,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const client = useQueryClient();
  const [notice, setNotice] = useState("");
  const [editorVersion, setEditorVersion] = useState(0);
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
  const saved = (value: AccountPreferences) => {
    client.setQueryData(["preferences"], value);
    setEditorVersion((v) => v + 1);
    setNotice("偏好已保存，下次开始新的选餐时生效。");
  };
  const reload = async () => {
    const result = await query.refetch();
    if (result.isSuccess) {
      setEditorVersion((v) => v + 1);
      setNotice("已读取最新偏好。");
    }
  };
  const learning = query.data?.learning;
  return (
    <>
      <header className="page-heading">
        <h1>你的用餐偏好</h1>
        <p>从多餐选择中总结，作为下一餐的默认条件。</p>
      </header>
      {learning && (
        <p className="muted" role="status">
          已记录 {learning.mealCount} 餐，满 {learning.nextLearningAt}{" "}
          餐再次总结。
          {learning.status === "queued" || learning.status === "running"
            ? " 正在总结偏好。"
            : ""}
          {learning.status === "failed"
            ? " 上次总结失败，仍使用已有默认值。"
            : ""}
          {learning.lastSuccessAt
            ? ` 最近总结：${new Date(learning.lastSuccessAt).toLocaleString("zh-CN")}`
            : ""}
        </p>
      )}
      <p className="muted">
        只自动学习预算、距离和补充说明；限定与排除食物由你设置。修改后保存会固定该字段。
      </p>
      {query.isError && query.data && (
        <p className="error" role="alert">
          {query.error.message}
        </p>
      )}
      {query.isPending ? (
        <p>正在读取偏好…</p>
      ) : query.data ? (
        <PreferenceEditor
          key={editorVersion}
          initial={query.data}
          onSaved={saved}
        />
      ) : query.isError ? (
        <div role="alert" className="error">
          {query.error.message}
          <button onClick={() => void reload()}>重新读取偏好</button>
        </div>
      ) : null}
      <Button
        variant="ghost"
        disabled={query.isFetching}
        onClick={() => void reload()}
      >
        重新读取偏好
      </Button>
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
