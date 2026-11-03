import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, Link } from "react-router-dom";
import { MapPin, ChevronRight } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PreferencesForm } from "../components/preferences-form";
import { Button } from "../components/ui/button";
import { Brand, PageHero } from "../components/brand";
import { useDraft } from "../lib/store";
import { useMealBusy } from "../lib/recommendations";
import { useAuth } from "../lib/auth";
import { configError, request } from "../lib/api";
import {
  type Preferences,
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
  const busy = useMealBusy();
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
      <header className="home-header">
        <Brand />
        <Link to="/map" className="location-link">
          <MapPin size={20} />
          <span>{draft.origin?.address || "选择出发地点"}</span>
          <ChevronRight size={18} />
        </Link>
      </header>
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
    </>
  );
}

function PreferenceEditor({
  initial,
  onSaved,
  busy,
  onSavingChange,
  children,
}: {
  initial: AccountPreferences;
  onSaved: (value: AccountPreferences) => void;
  busy: boolean;
  onSavingChange: (saving: boolean) => void;
  children: ReactNode;
}) {
  // Keep the editing baseline stable until an explicit save.
  const [baseline] = useState(initial);
  const [automatic, setAutomatic] = useState<LearnableField[]>([]);
  const save = async (p: Preferences) => {
    onSavingChange(true);
    try {
      const saved = await request(
        "/preferences",
        { revision: baseline.revision, overrides: editedOverrides(baseline, p, automatic) },
        "PUT",
        undefined,
        undefined,
        accountPreferencesSchema,
      );
      onSaved(saved);
    } finally {
      onSavingChange(false);
    }
  };
  return (
    <PreferencesForm
      initial={{ ...defaults, ...baseline.defaults }}
      onSubmit={save}
      busy={busy}
      personal
      label="保存偏好"
      memory={{
        sources: baseline.sources,
        overrides: baseline.overrides,
        automatic,
        onRestore: (key) => setAutomatic((current) =>
          current.includes(key) ? current.filter((field) => field !== key) : [...current, key],
        ),
      }}
    >{children}</PreferencesForm>
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
  const [updating, setUpdating] = useState(false);
  const [learningError, setLearningError] = useState("");
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
    setEditorVersion((version) => version + 1);
    setNotice("偏好已保存，下次开始新的选餐时生效。");
  };
  const updateLearning = async (enabled: boolean) => {
    setUpdating(true);
    setLearningError("");
    try {
      const value = await request(
        "/preferences/learning", { enabled }, "PATCH", undefined, undefined, accountPreferencesSchema,
      );
      // Do not remount the editor: switching learning must preserve unsaved edits.
      client.setQueryData(["preferences"], value);
      setNotice(enabled ? "偏好学习已开启" : "偏好学习已关闭");
    } catch (error) {
      setLearningError(error instanceof Error ? error.message : "偏好学习设置保存失败");
    } finally {
      setUpdating(false);
    }
  };
  const learning = query.data?.learning;
  const accountPanel = (
    <section className="account-panel" aria-label="当前账号">
      <div><strong>{auth.user?.displayName}</strong><p>@{auth.user?.username}</p></div>
      <Button type="button" variant="ghost" disabled={logoutBusy} onClick={() => void logout()}>
        {logoutBusy ? "正在退出…" : "退出登录"}<ChevronRight size={18} />
      </Button>
    </section>
  );
  return (
    <>
      <Brand />
      <PageHero className="profile-hero">
        <h1>你的用餐偏好</h1>
      {learning && (
        <section className="learning-control" aria-label="偏好学习">
          <div><strong>偏好学习</strong><p>每天总结已完成的选餐</p></div>
          <Button type="button" role="switch" aria-label="偏好学习" aria-checked={learning.enabled}
            className="learning-switch"
            variant={learning.enabled ? "default" : "outline"} disabled={updating}
            onClick={() => void updateLearning(!learning.enabled)}>
            <span className="switch-thumb" /><span className="sr-only">{learning.enabled ? "关闭偏好学习" : "开启偏好学习"}</span>
          </Button>
        </section>
      )}
      </PageHero>
      {learningError && <p className="error" role="alert">{learningError}</p>}
      {learning && (learning.status !== "idle" || learning.lastSuccessAt) && (
        <p className="muted" role="status">
          {learning.status === "queued" ? " 等待每日偏好总结。" : ""}
          {learning.status === "running" ? " 正在总结偏好。" : ""}
          {learning.status === "failed"
            ? " 上次总结失败，仍使用已有默认值。"
            : ""}
          {learning.lastSuccessAt
            ? ` 最近总结：${new Date(learning.lastSuccessAt).toLocaleString("zh-CN")}`
            : ""}
        </p>
      )}
      {query.isError && (
        <div className="error" role="alert">
          <p>{query.error.message}</p>
          <Button type="button" variant="ghost" disabled={query.isFetching} onClick={() => void query.refetch()}>
            重新读取偏好
          </Button>
        </div>
      )}
      {query.isPending ? (
        <p>正在读取偏好…</p>
      ) : query.data ? (
        <PreferenceEditor key={editorVersion} initial={query.data} onSaved={saved}
          busy={updating} onSavingChange={setUpdating} >{accountPanel}</PreferenceEditor>
      ) : null}
      {!query.data && accountPanel}
      <p role="status">{notice}</p>
      {logoutError && (
        <p role="alert" className="error">
          {logoutError}
        </p>
      )}
    </>
  );
}
