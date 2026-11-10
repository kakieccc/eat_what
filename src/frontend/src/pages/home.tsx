import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { MapPin, ChevronRight, KeyRound, Pencil } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { PreferencesForm } from "../components/preferences-form";
import { Button } from "../components/ui/button";
import { PageHero } from "../components/brand";
import { DesktopPageHeader } from "../components/desktop-page-header";
import { AccountForm, type AccountEditMode } from "../components/account-form";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "../components/ui/sheet";
import { useDraft } from "../lib/store";
import { useMealBusy } from "../lib/recommendations";
import { useAuth } from "../lib/auth";
import { useDesktop } from "../lib/use-desktop";
import { usePreferencePrefill, usePreferences } from "../lib/use-preferences";
import { request } from "../lib/api";
import {
  type Preferences,
  type AccountPreferences,
  defaults,
  toDecisionRequest,
  accountPreferencesSchema,
  editedOverrides,
} from "../lib/schemas";

export function Home() {
  const draft = useDraft(),
    navigate = useNavigate();
  const saved = usePreferencePrefill();
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
    navigate("/discover");
  };
  return (
    <>
      {saved.isError && (
        <p role="alert" className="error">
          账户偏好读取失败，请检查本次条件。
        </p>
      )}
      {!draft.hasDraft ? (
        <p>正在读取偏好…</p>
      ) : (
        <PreferencesForm
          key={draft.prefill?.revision ?? "draft"}
          initial={draft.preferences}
          onSubmit={submit}
          onDraftChange={draft.setPreferences}
          busy={busy}
          label="帮我选一家"
          headingAction={<Link to="/map" className="location-link"
            title={draft.origin?.address || "选择地点"}
            aria-label={draft.origin?.address ? `出发地点：${draft.origin.address}，点击更换` : "选择地点"}>
            <MapPin size={20} aria-hidden="true" />
            <span>{draft.origin?.address || "选择地点"}</span>
            <ChevronRight size={18} aria-hidden="true" />
          </Link>}
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
}: {
  initial: AccountPreferences;
  onSaved: (value: AccountPreferences) => void;
  busy: boolean;
  onSavingChange: (saving: boolean) => void;
}) {
  // Keep the editing baseline stable until an explicit save.
  const [baseline] = useState(initial);
  const save = async (p: Preferences) => {
    onSavingChange(true);
    try {
      const saved = await request(
        "/preferences",
        { revision: baseline.revision, overrides: editedOverrides(baseline, p) },
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
    />
  );
}

export function Profile() {
  const desktop = useDesktop();
  const auth = useAuth(),
    navigate = useNavigate();
  const query = usePreferences();
  const client = useQueryClient();
  const [notice, setNotice] = useState("");
  const [editorVersion, setEditorVersion] = useState(0);
  const [updating, setUpdating] = useState(false);
  const [learningError, setLearningError] = useState("");
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [accountMode, setAccountMode] = useState<AccountEditMode>("name");
  const [accountOpen, setAccountOpen] = useState(false);
  const [accountNotice, setAccountNotice] = useState("");
  const editAccount = (mode: AccountEditMode) => {
    setAccountMode(mode);
    setAccountNotice("");
    setAccountOpen(true);
  };
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
    setNotice("偏好已保存。");
  };
  const updateLearning = async (enabled: boolean) => {
    setUpdating(true);
    setLearningError("");
    setNotice("");
    try {
      const value = await request(
        "/preferences/learning", { enabled }, "PATCH", undefined, undefined, accountPreferencesSchema,
      );
      // Do not remount the editor: switching learning must preserve unsaved edits.
      client.setQueryData(["preferences"], value);
    } catch (error) {
      setLearningError(error instanceof Error ? error.message : "偏好学习设置保存失败");
    } finally {
      setUpdating(false);
    }
  };
  const learning = query.data?.learning;
  const logoutButton = (
    <Button type="button" variant={desktop ? "ghost" : "outline"} className="logout-button" disabled={logoutBusy} onClick={() => void logout()}>
      {logoutBusy ? "正在退出…" : "退出登录"}{desktop && <ChevronRight size={18} aria-hidden="true" />}
    </Button>
  );
  const passwordButton = (
    <Button type="button" variant={desktop ? "outline" : "ghost"} className="account-password" disabled={logoutBusy} onClick={() => editAccount("password")}>
      <KeyRound data-icon="inline-start" />修改密码
    </Button>
  );
  const learningControl = learning && (
    <section className="learning-control" aria-label="偏好学习">
      <strong>偏好学习</strong>
      <Button type="button" role="switch" aria-label="偏好学习" aria-checked={learning.enabled}
        className="learning-switch"
        variant={learning.enabled ? "default" : "outline"} disabled={updating}
        onClick={() => void updateLearning(!learning.enabled)}>
        <span className="switch-thumb" />
      </Button>
    </section>
  );
  const accountPanel = (
    <section className="account-panel" aria-label="当前账号">
      <div>
        <div className="account-name-row">
          <Button type="button" variant="ghost" className="account-name" disabled={logoutBusy}
            aria-label={`修改昵称：${auth.user?.displayName}`} onClick={() => editAccount("name")}>
            <strong>{auth.user?.displayName}</strong><Pencil data-icon="inline-end" aria-hidden="true" />
          </Button>
          {!desktop && passwordButton}
        </div>
        <div className="account-user-row">
          <p className="account-username" title={`@${auth.user?.username}`}>@{auth.user?.username}</p>
          {!desktop && learningControl}
        </div>
      </div>
      {desktop && learningControl}
      {desktop && <div className="account-actions">
        {passwordButton}
        {logoutButton}
      </div>}
      {accountNotice && <p role="status">{accountNotice}</p>}
      {desktop && logoutError && <p role="alert" className="error">{logoutError}</p>}
    </section>
  );
  return (
    <>
      {desktop ? <DesktopPageHeader title="你的用餐偏好" description="设置常用条件，让下一次选餐更合心意。" /> : <PageHero className="profile-hero">
        <h1>你的用餐偏好</h1>
      </PageHero>}
      <div className={desktop ? "desktop-profile-layout" : "mobile-profile-layout"}>
      <aside className={desktop ? "desktop-profile-account" : "mobile-profile-account"}>
      {accountPanel}
      {learningError && <p className="error" role="alert">{learningError}</p>}
      </aside>
      <div className="profile-editor">
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
          busy={updating} onSavingChange={setUpdating} />
      ) : null}
      <p role="status">{notice}</p>
      </div>
      </div>
      {!desktop && <div className="mobile-profile-logout">
        {logoutButton}
        {logoutError && <p role="alert" className="error">{logoutError}</p>}
      </div>}
      <Sheet open={accountOpen} onOpenChange={setAccountOpen}>
        <SheetContent side="bottom" className="advanced-sheet account-sheet">
          <SheetHeader className="account-sheet-heading">
            <SheetTitle>{accountMode === "name" ? "修改显示名称" : "修改密码"}</SheetTitle>
            <SheetDescription>
              {accountMode === "name" ? "设置页面上显示的名称，最多 40 个字符。" : "修改后所有设备均需使用新密码重新登录。"}
            </SheetDescription>
          </SheetHeader>
          <AccountForm key={accountMode} mode={accountMode} onNameSaved={() => {
            setAccountOpen(false);
            setAccountNotice("显示名称已更新。");
          }} />
        </SheetContent>
      </Sheet>
    </>
  );
}
