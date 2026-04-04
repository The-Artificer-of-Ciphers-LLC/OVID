import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { isAuthenticated, clearAuth, useAuth, exchangeAuthCode } from "@/lib/auth";

// ---------------------------------------------------------------------------
// document.cookie mock
// ---------------------------------------------------------------------------
let cookieStore: Record<string, string> = {};

Object.defineProperty(document, "cookie", {
  get: () =>
    Object.entries(cookieStore)
      .map(([k, v]) => `${k}=${v}`)
      .join("; "),
  set: (value: string) => {
    const [pair] = value.split(";");
    const [key, val] = pair.split("=");
    if (value.includes("expires=Thu, 01 Jan 1970")) {
      delete cookieStore[key.trim()];
    } else {
      cookieStore[key.trim()] = val?.trim() ?? "";
    }
  },
});

// ---------------------------------------------------------------------------
// Cookie helper tests
// ---------------------------------------------------------------------------

describe("Cookie auth helpers", () => {
  beforeEach(() => {
    cookieStore = {};
    vi.clearAllMocks();
  });

  it("isAuthenticated returns false when no ovid_auth cookie", () => {
    expect(isAuthenticated()).toBe(false);
  });

  it("isAuthenticated returns true when ovid_auth cookie is 1", () => {
    cookieStore["ovid_auth"] = "1";
    expect(isAuthenticated()).toBe(true);
  });

  it("clearAuth removes ovid_auth cookie", () => {
    cookieStore["ovid_auth"] = "1";
    clearAuth();
    expect(isAuthenticated()).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// exchangeAuthCode tests
// ---------------------------------------------------------------------------

describe("exchangeAuthCode", () => {
  beforeEach(() => {
    cookieStore = {};
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("posts code to /v1/auth/token and returns true on success", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ authenticated: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await exchangeAuthCode("test-code");
    expect(result).toBe(true);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/v1/auth/token"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
      }),
    );
  });

  it("returns false when exchange fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ error: "invalid_code" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await exchangeAuthCode("bad-code");
    expect(result).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// useAuth hook tests
// ---------------------------------------------------------------------------

describe("useAuth", () => {
  beforeEach(() => {
    cookieStore = {};
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("returns loading=false with null user when not authenticated", async () => {
    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toBeNull();
  });

  it("fetches user from /v1/auth/me when ovid_auth cookie is set", async () => {
    const mockUser = {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
      display_name: "Test User",
      role: "user",
      email_verified: true,
    };

    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(mockUser), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    cookieStore["ovid_auth"] = "1";

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toEqual(mockUser);
  });

  it("clears auth and returns null user when /v1/auth/me fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ error: "unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    cookieStore["ovid_auth"] = "1";

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toBeNull();
  });

  it("logout clears user", async () => {
    const mockUser = {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
      display_name: "Test User",
      role: "user",
      email_verified: true,
    };

    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(mockUser), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    cookieStore["ovid_auth"] = "1";

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toEqual(mockUser);

    act(() => {
      result.current.logout();
    });

    expect(result.current.user).toBeNull();
  });
});
