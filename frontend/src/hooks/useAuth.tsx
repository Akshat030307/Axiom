"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import * as api from "@/lib/api";
import type { User } from "@/types/api";

interface AuthTokens {
  access_token: string;
  refresh_token: string;
}

interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  loading: boolean;
  bootstrapping: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => void;
  refreshAccessToken: () => Promise<string>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// NOTE(security): the refresh token is persisted in sessionStorage so a page
// refresh doesn't destroy the session — the live workspace's WebSocket needs
// a token to reconnect with on load (Phase 4 DoD: "WebSocket survives a
// mid-run browser refresh via the snapshot frame"), which is impossible if
// the whole session lived only in React state. PRD §15.3 specifies an
// httpOnly cookie instead, specifically because httpOnly storage can't be
// read by JS and sessionStorage can — this is XSS-exposed in a way the
// spec'd approach isn't. Accepted tradeoff for the Wednesday demo; the
// correct fix is issuing the refresh token as an httpOnly cookie from the
// backend and switching this client to `credentials: "include"` instead of
// storing/sending it manually.
const REFRESH_TOKEN_KEY = "research-agent:refresh_token";

function readStoredRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(REFRESH_TOKEN_KEY);
}

function writeStoredRefreshToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.sessionStorage.setItem(REFRESH_TOKEN_KEY, token);
  else window.sessionStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // True until the boot-time session-resume attempt below has settled, so
  // route guards can wait instead of bouncing straight to /login.
  const [bootstrapping, setBootstrapping] = useState(true);
  const refreshTokenRef = useRef<string | null>(null);
  const hasBootstrapped = useRef(false);

  const applySession = useCallback((tokens: AuthTokens, sessionUser: User) => {
    refreshTokenRef.current = tokens.refresh_token;
    writeStoredRefreshToken(tokens.refresh_token);
    setAccessToken(tokens.access_token);
    setUser(sessionUser);
  }, []);

  const clearSession = useCallback(() => {
    refreshTokenRef.current = null;
    writeStoredRefreshToken(null);
    setAccessToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    // Guards against React Strict Mode's intentional double-invoke of
    // effects in dev: without this, two concurrent /auth/refresh calls fire
    // with the same (single-use, rotating) stored token — the second one
    // hits an already-revoked token, fails, and wipes a session that had
    // just logged in successfully.
    if (hasBootstrapped.current) return;
    hasBootstrapped.current = true;

    const stored = readStoredRefreshToken();
    if (!stored) {
      setBootstrapping(false);
      return;
    }
    (async () => {
      try {
        const tokens = await api.refresh(stored);
        const sessionUser = await api.me(tokens.access_token);
        applySession(tokens, sessionUser);
      } catch {
        writeStoredRefreshToken(null);
      } finally {
        setBootstrapping(false);
      }
    })();
    // Intentionally runs once on mount only — applySession is a stable
    // useCallback with no deps, so this isn't missing a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      setLoading(true);
      try {
        const res = await api.login(email, password);
        applySession(res, res.user);
      } finally {
        setLoading(false);
      }
    },
    [applySession]
  );

  const register = useCallback(
    async (email: string, password: string, displayName?: string) => {
      setLoading(true);
      try {
        const res = await api.register(email, password, displayName);
        applySession(res, res.user);
      } finally {
        setLoading(false);
      }
    },
    [applySession]
  );

  const logout = useCallback(() => {
    const stored = refreshTokenRef.current;
    clearSession();
    if (stored) void api.logout(stored);
  }, [clearSession]);

  // Exposed so useResearchSocket can recover from a 4401 WS close (access
  // token expired mid-run — realistic on a deep run brushing the 15-minute
  // access-token lifetime) by minting a fresh access token without tearing
  // down the whole session.
  const refreshAccessToken = useCallback(async (): Promise<string> => {
    const stored = refreshTokenRef.current;
    if (!stored) throw new Error("No refresh token available");
    const tokens = await api.refresh(stored);
    refreshTokenRef.current = tokens.refresh_token;
    writeStoredRefreshToken(tokens.refresh_token);
    setAccessToken(tokens.access_token);
    return tokens.access_token;
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, accessToken, loading, bootstrapping, login, register, logout, refreshAccessToken }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
