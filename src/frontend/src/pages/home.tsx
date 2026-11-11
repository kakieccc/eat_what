import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { MapPin, ChevronRight, Settings } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { PreferencesForm } from "../components/preferences-form";
import { Button } from "../components/ui/button";
import { Brand, PageHero } from "../components/brand";
import { DesktopPageHeader } from "../components/desktop-page-header";
import { AccountSettings } from "../components/account-settings";
import { Sheet, SheetTrigger } from "../components/ui/sheet";
import { useDraft } from "../lib/store";
import { useMealBusy } from "../lib/recommendations";
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
  const query = usePreferences();
  const client = useQueryClient();
  const [notice, setNotice] = useState("");
  const [editorVersion, setEditorVersion] = useState(0);
  const [updating, setUpdating] = useState(false);
  const [learningError, setLearningError] = useState("");
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
  const learningControl = learning && (
    <section className="learning-control" aria-label="偏好学习">
      <div>
        <strong>偏好学习</strong>
        <p>根据用餐记录更新常用偏好</p>
      </div>
      <Button type="button" role="switch" aria-label="偏好学习" aria-checked={learning.enabled}
        className="learning-switch"
        variant={learning.enabled ? "default" : "outline"} disabled={updating}
        onClick={() => void updateLearning(!learning.enabled)}>
        <span className="switch-thumb" />
      </Button>
    </section>
  );
  const settingsTrigger = (
    <SheetTrigger asChild>
      <Button type="button" variant="outline" size="icon" className="profile-settings-trigger" aria-label="账号设置" title="账号设置">
        <Settings className="size-5" aria-hidden="true" />
      </Button>
    </SheetTrigger>
  );
  return (
    <Sheet>
      {desktop ? <DesktopPageHeader title="你的用餐偏好" description="设置常用条件，让下一次选餐更合心意。">
        {settingsTrigger}
      </DesktopPageHeader> : <PageHero className="profile-hero">
        <div className="mobile-brand-row"><Brand />{settingsTrigger}</div>
        <h1>你的用餐偏好</h1>
      </PageHero>}
      <div className={desktop ? "desktop-profile-layout" : "mobile-profile-layout"}>
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
      <AccountSettings>
        {learningControl}
        {learningError && <p className="error" role="alert">{learningError}</p>}
      </AccountSettings>
    </Sheet>
  );
}
