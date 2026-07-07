"use client";

import { useState, useEffect, useCallback } from "react";
import { getMe, type UserResponse } from "@/lib/api";

// ---------------------------------------------------------------------------
// Token helpers (localStorage, guarded for SSR)
// ---------------------------------------------------------------------------

const TOKEN_KEY = "ovid_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}

// ---------------------------------------------------------------------------
// useAuth hook
// ---------------------------------------------------------------------------

export interface AuthState {
  user: UserResponse | null;
  token: string | null;
  loading: boolean;
  logout: () => void;
}

export function useAuth(): AuthState {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    // Run the auth check as an async continuation so the loading-state
    // update always happens in a callback rather than synchronously in the
    // effect body (react-hooks/set-state-in-effect).
    (async () => {
      const stored = getToken();
      if (!stored) {
        return;
      }

      setTokenState(stored);

      try {
        const u = await getMe(stored);
        if (!cancelled) setUser(u);
      } catch {
        // Token is invalid or expired — clear it
        if (!cancelled) {
          clearToken();
          setTokenState(null);
        }
      }
    })().finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
    setUser(null);
  }, []);

  return { user, token, loading, logout };
}
