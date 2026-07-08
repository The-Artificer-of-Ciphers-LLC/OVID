"use client";

import { useState, useEffect, useCallback } from "react";
import { getMe, type UserResponse, ApiError } from "@/lib/api";

// A transient /me failure (network blip, 5xx) must not wipe a valid token —
// wait a beat and retry once before giving up (UAT gap G-07-4).
const TRANSIENT_RETRY_DELAY_MS = 600;

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
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          // Token is genuinely invalid or expired — clear it.
          if (!cancelled) {
            clearToken();
            setTokenState(null);
          }
        } else {
          // Transient failure (network error, non-401 status like a 5xx) —
          // clearing the token here would permanently wipe a VALID token
          // over a blip a refresh could have recovered from. Retry once
          // after a short delay so it can self-heal; if the retry also
          // fails transiently, keep the token and leave `user` null for
          // this load only (UAT gap G-07-4).
          await new Promise((resolve) => setTimeout(resolve, TRANSIENT_RETRY_DELAY_MS));
          if (cancelled) return;

          try {
            const u = await getMe(stored);
            if (!cancelled) setUser(u);
          } catch (retryErr) {
            if (!cancelled && retryErr instanceof ApiError && retryErr.status === 401) {
              clearToken();
              setTokenState(null);
            }
            // Otherwise still transient — keep the token, `user` stays null.
          }
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
