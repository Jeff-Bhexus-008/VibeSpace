import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, ApiError } from "@/lib/api";
import type { SessionUser } from "@/types/api";

interface AuthState {
  user: SessionUser | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  register: (input: { username: string; email: string; password: string; display_name?: string }) => Promise<{
    verification_email_sent: boolean;
    dev_verify_link?: string | null;
  }>;
  signOut: () => Promise<void>;
  refresh: () => Promise<SessionUser | null>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (): Promise<SessionUser | null> => {
    try {
      const me = await api.get<SessionUser>("/auth/me");
      setUser(me);
      return me;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setUser(null);
        return null;
      }
      throw error;
    }
  }, []);

  useEffect(() => {
    void refresh().finally(() => setLoading(false));
  }, [refresh]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const session = await api.post<{ user: SessionUser }>("/auth/login", { email, password });
      setUser(session.user);
    },
    [],
  );

  const register = useCallback(
    async (input: { username: string; email: string; password: string; display_name?: string }) => {
      const result = await api.post<{
        user: SessionUser;
        verification_email_sent: boolean;
        dev_verify_link?: string | null;
      }>("/auth/register", input);
      setUser(result.user);
      return {
        verification_email_sent: result.verification_email_sent,
        dev_verify_link: result.dev_verify_link,
      };
    },
    [],
  );

  const signOut = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, loading, signIn, register, signOut, refresh }),
    [user, loading, signIn, register, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}