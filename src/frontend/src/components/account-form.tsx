import { useState, type FormEvent } from "react";
import { useAuth } from "../lib/auth";
import { Button } from "./ui/button";

export type AccountEditMode = "name" | "password";

export function AccountForm({ mode, onNameSaved }: {
  mode: AccountEditMode;
  onNameSaved: () => void;
}) {
  const auth = useAuth();
  const [displayName, setDisplayName] = useState(auth.user?.displayName ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = displayName.trim();
    if (mode === "name" && !name) {
      setError("显示名称不能为空");
      return;
    }
    if (mode === "password" && newPassword !== confirmation) {
      setError("两次输入的新密码不一致");
      return;
    }
    setSaving(true);
    setError("");
    try {
      if (mode === "name") {
        await auth.updateName(name);
        onNameSaved();
      } else {
        await auth.changePassword(currentPassword, newPassword);
        // Reload after logout so the auth guard cannot replace the success notice.
        window.location.replace("/login?passwordChanged=1");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存失败，请稍后重试");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="account-form" onSubmit={submit} onChange={() => setError("")}>
      <fieldset className="account-form-fields" disabled={saving}>
        {mode === "name" ? (
          <label className="field-label">显示名称
            <input required maxLength={40} autoComplete="nickname" placeholder="输入显示名称"
              value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </label>
        ) : (
          <>
            <label className="field-label">当前密码
              <input required type="password" maxLength={128} autoComplete="current-password"
                value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
            </label>
            <label className="field-label">新密码
              <input required type="password" minLength={8} maxLength={128} autoComplete="new-password"
                placeholder="8–128 位字符" value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)} />
            </label>
            <label className="field-label">确认新密码
              <input required type="password" minLength={8} maxLength={128} autoComplete="new-password"
                placeholder="再次输入新密码" value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)} />
            </label>
          </>
        )}
      </fieldset>
      {error && <p className="error" role="alert">{error}</p>}
      <Button type="submit" className="primary-full" disabled={saving}>
        {saving ? "正在保存…" : mode === "name" ? "保存名称" : "确认修改密码"}
      </Button>
    </form>
  );
}
