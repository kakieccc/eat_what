import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { advanceSession, getSessionVersion, configError, endpoint, request, setCsrfToken, setUnauthorizedHandler } from "./api";
import { useDraft } from "./store";
import { notifyAuthChanged, watchAuthChanges, withAuthLock } from "./auth-sync";

export type User = {
  id: string;
  username: string;
  displayName: string;
  createdAt: string;
};
type AuthPayload = { user: User; csrfToken: string };
type AuthState = "loading" | "anonymous" | "authenticated" | "error";
type AuthContextValue = {
  state: AuthState;
  user: User | null;
  retrySession: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, displayName: string) => Promise<void>;
  updateName: (displayName: string) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  logout: () => Promise<void>;
};

const Context = createContext<AuthContextValue | null>(null);

async function readSession(signal?: AbortSignal): Promise<AuthPayload | null> {
  const response = await fetch(endpoint("/auth/me"), {
    credentials: "include", cache: "no-store", signal,
  });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("无法检查登录状态");
  const payload = await response.json();
  const data = payload.data as AuthPayload | undefined;
  if (!payload.success || !data?.user || !data.csrfToken)
    throw new Error("登录状态响应无效");
  return data;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [state, setState] = useState<AuthState>("loading");
  const [user, setUser] = useState<User | null>(null);
  const pendingChanges = useRef(0);

  const clearLocal = useCallback(() => {
    void client.cancelQueries();
    client.clear();
    useDraft.getState().reset();
    setCsrfToken(null);
    setUser(null);
  }, [client]);
  const becomeAnonymous = useCallback(() => {
    advanceSession();
    clearLocal();
    setState("anonymous");
  }, [clearLocal]);
  useEffect(() => {
    setUnauthorizedHandler(becomeAnonymous);
    return () => setUnauthorizedHandler(null);
  }, [becomeAnonymous]);
  const establish = useCallback((data: AuthPayload | null) => {
    if (!data) {
      becomeAnonymous();
      return;
    }
    if (useDraft.getState().ownerId !== data.user.id) {
      clearLocal();
      useDraft.getState().setOwnerId(data.user.id);
    }
    setCsrfToken(data.csrfToken);
    setUser(data.user);
    setState("authenticated");
  }, [becomeAnonymous, clearLocal]);
  const loadSession = useCallback(async (signal?: AbortSignal, reset = false) => {
    // A queued account change will reconcile the session before releasing its lock.
    if (pendingChanges.current) return;
    const version = advanceSession();
    const stale = () => signal?.aborted || version !== getSessionVersion();
    if (reset) clearLocal();
    if (configError) {
      setState("error");
      return;
    }
    setState("loading");
    try {
      await withAuthLock(async () => {
        if (stale()) return;
        const data = await readSession(signal);
        if (!stale()) establish(data);
      });
    } catch {
      if (!stale()) setState("error");
    }
  }, [clearLocal, establish]);
  useEffect(() => {
    const controller = new AbortController();
    void loadSession(controller.signal);
    return () => { controller.abort(); advanceSession(); };
  }, [loadSession]);
  useEffect(() => watchAuthChanges(() => { void loadSession(undefined, true); }), [loadSession]);

  const changeSession = async (path: string, body: unknown, forCurrentUser = false) => {
    const expectedUserId = user?.id;
    pendingChanges.current++;
    try {
      await withAuthLock(async () => {
        advanceSession();
        let changed = false;
        let failure: unknown;
        try {
          if (forCurrentUser) {
            const current = await readSession();
            if (!current || current.user.id !== expectedUserId)
              throw new Error("账号已在其他标签页变更，请确认当前账号后重试");
            setCsrfToken(current.csrfToken);
          }
          await request(path, body);
          changed = true;
        } catch (error) {
          failure = error;
        }
        // Set-Cookie may already have been applied even when reading the response failed.
        advanceSession();
        try {
          const current = await readSession();
          if (changed) clearLocal();
          establish(current);
        } catch (error) {
          clearLocal();
          setState("error");
          throw error;
        } finally {
          notifyAuthChanged();
        }
        if (!changed) throw failure;
      });
    } finally {
      pendingChanges.current--;
    }
  };
  const login = async (username: string, password: string) => {
    await changeSession("/auth/login", { username, password });
  };
  const register = async (username: string, password: string, displayName: string) => {
    await changeSession("/auth/register", {
      username, password, displayName: displayName.trim(),
    });
  };
  const updateName = async (displayName: string) => {
    const version = getSessionVersion();
    const data = await request<User>("/auth/me", { displayName }, "PATCH");
    if (version === getSessionVersion()) setUser(data);
  };
  const changePassword = async (currentPassword: string, newPassword: string) => {
    await changeSession("/auth/change-password", {
      currentPassword, newPassword,
    }, true);
  };
  const logout = async () => {
    await changeSession("/auth/logout", {}, true);
  };
  return <Context.Provider value={{
    state, user, retrySession: () => loadSession(),
    login, register, updateName, changePassword, logout,
  }}>{children}</Context.Provider>;
}

export function useAuth() {
  const value = useContext(Context);
  if (!value) throw new Error("AuthProvider is missing");
  return value;
}
