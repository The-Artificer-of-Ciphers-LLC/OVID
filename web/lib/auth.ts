"use client";

import { useState, useEffect, useCallback } from "react";
import { getMe, type UserResponse } from "@/lib/api";

// ---------------------------------------------------------------------------
// Cookie helpers (HttpOnly cookies are not readable by JS, but the
// ovid_auth flag cookie IS readable to detect auth state)
// ---------------------------------------------------------------------------

const AUTH_FLAG_COOKIE = "ovid_auth";

function _getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function _deleteCookie(name: string): void {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
}

/**
 * Check if the user is authenticated by reading the ovid_auth flag cookie.
 * The actual auth token is in an HttpOnly cookie (not accessible to JS).
 */
export function isAuthenticated(): boolean {
  return _getCookie(AUTH_FLAG_COOKIE) === "1";
}

/**
 * Exchange an auth code (from OAuth callback URL) for HttpOnly auth cookies.
 * The API sets the cookies in the response, so the browser stores them
 * automatically when credentials: "include" is used.
 */
export async function exchangeAuthCode(code: string): Promise<boolean> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const resp = await fetch(`${baseUrl}/v1/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ code }),
  });
  return resp.ok;
}

/**
 * Clear auth state by deleting the flag cookie and calling logout.
 * The HttpOnly ovid_token cookie can only be cleared by the server
 * or by expiry, but removing ovid_auth is sufficient for the UI.
 */
export function clearAuth(): void {
  _deleteCookie(AUTH_FLAG_COOKIE);
  _deleteCookie("ovid_auth");
}

// ---------------------------------------------------------------------------
// useAuth hook
// ---------------------------------------------------------------------------

export interface AuthState {
  user: UserResponse | null;
  loading: boolean;
  logout: () => void;
}

export function useAuth(): AuthState {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated()) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    getMe()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        // Cookie is invalid or expired -- clear auth state
        if (!cancelled) {
          clearAuth();
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setUser(null);
  }, []);

  return { user, loading, logout };
}
