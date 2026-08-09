"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

import * as api from "@/lib/api";
import type { User } from "@/types/api";

interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// Phase 1: access token held in memory only (React state), no localStorage,
// no httpOnly cookie plumbing yet — a page refresh logs the user out. That's
// an accepted simplification for "login plus a form"; PRD §15.3's httpOnly
// cookie guidance is a Phase 4 item. No auto-refresh is wired up either — an
// expired 15-minute access token just surfaces as a 401 on the next call.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true);
    try {
      const res = await api.login(email, password);
      setUser(res.user);
      setAccessToken(res.access_token);
    } finally {
      setLoading(false);
    }
  }, []);

  const register = useCallback(async (email: string, password: string, displayName?: string) => {
    setLoading(true);
    try {
      const res = await api.register(email, password, displayName);
      setUser(res.user);
      setAccessToken(res.access_token);
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    setAccessToken(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, accessToken, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
