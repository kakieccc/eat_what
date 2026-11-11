import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ChevronRight, KeyRound, LogOut, Pencil } from "lucide-react";
import { useAuth } from "../lib/auth";
import { useDesktop } from "../lib/use-desktop";
import { AccountForm, type AccountEditMode } from "./account-form";
import { Button } from "./ui/button";
import { SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./ui/sheet";

export function AccountSettings({ children }: { children: ReactNode }) {
  const auth = useAuth(), navigate = useNavigate();
  const desktop = useDesktop();
  const [mode, setMode] = useState<AccountEditMode | null>(null);
  const [notice, setNotice] = useState("");
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const side = desktop ? "right" : "bottom";
  const editAccount = (next: AccountEditMode) => {
    setMode(next);
    setNotice("");
  };
  const logout = async () => {
    setLogoutBusy(true);
    setLogoutError("");
    try {
      await auth.logout();
      navigate("/login", { replace: true });
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : "退出失败");
    } finally {
      setLogoutBusy(false);
    }
  };
  return (
    <SheetContent side={side} data-side={side} className="account-sheet"
      aria-describedby={mode === "name" ? "account-description" : undefined}
      onCloseAutoFocus={() => {
        setMode(null);
        setNotice("");
        setLogoutError("");
      }}>
      <SheetHeader className="account-sheet-heading">
        <div className="account-settings-heading">
          {mode && <Button type="button" variant="ghost" size="icon" aria-label="返回账号设置" onClick={() => setMode(null)}>
            <ArrowLeft aria-hidden="true" />
          </Button>}
          <SheetTitle>{mode === "name" ? "修改显示名称" : mode === "password" ? "修改密码" : "账号设置"}</SheetTitle>
        </div>
        {mode === "name" && <SheetDescription id="account-description">
          设置页面上显示的名称，最多 40 个字符。
        </SheetDescription>}
      </SheetHeader>
      {mode ? <AccountForm key={mode} mode={mode} onNameSaved={() => {
        setMode(null);
        setNotice("显示名称已更新。");
      }} /> : <div className="account-settings">
        <dl className="account-details">
          <div><dt>用户名</dt><dd><span>@{auth.user?.username}</span></dd></div>
          <div><dt>显示名称</dt><dd>
            <strong>{auth.user?.displayName}</strong>
            <Button type="button" variant="ghost" disabled={logoutBusy} aria-label="修改显示名称" onClick={() => editAccount("name")}>
              <Pencil data-icon="inline-start" />修改
            </Button>
          </dd></div>
        </dl>
        {notice && <p role="status">{notice}</p>}
        {children}
        <Button type="button" variant="outline" className="account-setting-action" disabled={logoutBusy} onClick={() => editAccount("password")}>
          <span><KeyRound aria-hidden="true" />修改密码</span><ChevronRight aria-hidden="true" />
        </Button>
        <Button type="button" variant="ghost" className="account-setting-action" disabled={logoutBusy} onClick={() => void logout()}>
          <span><LogOut aria-hidden="true" />{logoutBusy ? "正在退出…" : "退出登录"}</span><ChevronRight aria-hidden="true" />
        </Button>
        {logoutError && <p role="alert" className="error">{logoutError}</p>}
      </div>}
    </SheetContent>
  );
}
