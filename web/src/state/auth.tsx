import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api } from "../lib/api";
import type { User } from "../lib/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, name: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  deleteAccount: (password: string) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try { localStorage.removeItem("at-token"); } catch { /* Storage may be unavailable. */ }
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const onUnauthorized = () => {
      queryClient.clear();
      setUser(null);
    };
    window.addEventListener("at-unauthorized", onUnauthorized);
    return () => window.removeEventListener("at-unauthorized", onUnauthorized);
  }, [queryClient]);

  const signIn = useCallback(async (email: string, password: string) => {
    const response = await api.login({ email, password });
    queryClient.clear();
    setUser(response);
  }, [queryClient]);

  const signUp = useCallback(async (email: string, name: string, password: string) => {
    const response = await api.register({ email, name, password });
    queryClient.clear();
    setUser(response);
  }, [queryClient]);

  const signOut = useCallback(async () => {
    await api.logout();
    queryClient.clear();
    setUser(null);
  }, [queryClient]);

  const deleteAccount = useCallback(async (password: string) => {
    await api.deleteAccount(password);
    queryClient.clear();
    setUser(null);
  }, [queryClient]);

  const value = useMemo(
    () => ({ user, loading, signIn, signUp, signOut, deleteAccount }),
    [user, loading, signIn, signUp, signOut, deleteAccount],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
