import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { advanceSession, getSessionVersion, configError, endpoint, request, setCsrfToken, setUnauthorizedHandler } from "./api";
import { safeSessionStorage } from "./storage";
import { useDraft } from "./store";

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

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [state, setState] = useState<AuthState>("loading");
  const [user, setUser] = useState<User | null>(null);

  const clearLocal = useCallback(() => {
    void client.cancelQueries();
    client.clear();
    useDraft.getState().reset();
    safeSessionStorage.removeItem("food-start");
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
  const loadSession = useCallback(async (signal?: AbortSignal) => {
    const version = advanceSession();
    const stale = () => signal?.aborted || version !== getSessionVersion();
    if (configError) {
      setState("error");
      return;
    }
    setState("loading");
    try {
      const response = await fetch(endpoint("/auth/me"), {
        credentials: "include",
        signal,
      });
      if (stale()) return;
      if (response.status === 401) {
        becomeAnonymous();
        return;
      }
      if (!response.ok) throw new Error("无法检查登录状态");
      const payload = await response.json();
      if (stale()) return;
      const data = payload.data as AuthPayload | undefined;
      if (!payload.success || !data?.user || !data.csrfToken)
        throw new Error("登录状态响应无效");
      if (useDraft.getState().ownerId !== data.user.id) {
        clearLocal();
        useDraft.getState().setOwnerId(data.user.id);
      }
      setCsrfToken(data.csrfToken);
      setUser(data.user);
      setState("authenticated");
    } catch {
      if (!stale()) setState("error");
    }
  }, [becomeAnonymous, clearLocal]);
  useEffect(() => {
    const controller = new AbortController();
    void loadSession(controller.signal);
    return () => { controller.abort(); advanceSession(); };
  }, [loadSession]);

  const establish = (data: AuthPayload) => {
    clearLocal();
    useDraft.getState().setOwnerId(data.user.id);
    setCsrfToken(data.csrfToken);
    setUser(data.user);
    setState("authenticated");
  };
  const login = async (username: string, password: string) => {
    const version = advanceSession();
    const data = await request<AuthPayload>("/auth/login", { username, password });
    if (version === getSessionVersion()) establish(data);
  };
  const register = async (username: string, password: string, displayName: string) => {
    const version = advanceSession();
    const data = await request<AuthPayload>("/auth/register", {
      username, password, displayName: displayName.trim(),
    });
    if (version === getSessionVersion()) establish(data);
  };
  const updateName = async (displayName: string) => {
    const version = getSessionVersion();
    const data = await request<User>("/auth/me", { displayName }, "PATCH");
    if (version === getSessionVersion()) setUser(data);
  };
  const changePassword = async (currentPassword: string, newPassword: string) => {
    const version = advanceSession();
    await request<{ loggedOut: boolean }>("/auth/change-password", {
      currentPassword, newPassword,
    });
    if (version === getSessionVersion()) becomeAnonymous();
  };
  const logout = async () => {
    const version = advanceSession();
    await request<{ loggedOut: boolean }>("/auth/logout", {});
    if (version === getSessionVersion()) becomeAnonymous();
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
