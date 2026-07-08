import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { getToken, setToken, clearToken, useAuth } from "@/lib/auth";

// ---------------------------------------------------------------------------
// localStorage mock
// ---------------------------------------------------------------------------
const storage: Record<string, string> = {};
const localStorageMock = {
  getItem: vi.fn((key: string) => storage[key] ?? null),
  setItem: vi.fn((key: string, value: string) => {
    storage[key] = value;
  }),
  removeItem: vi.fn((key: string) => {
    delete storage[key];
  }),
  clear: vi.fn(() => {
    for (const k of Object.keys(storage)) delete storage[k];
  }),
  get length() {
    return Object.keys(storage).length;
  },
  key: vi.fn(() => null),
};

Object.defineProperty(globalThis, "localStorage", { value: localStorageMock });

// ---------------------------------------------------------------------------
// Token helper tests
// ---------------------------------------------------------------------------

describe("Token helpers", () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  it("getToken returns null when no token is stored", () => {
    expect(getToken()).toBeNull();
  });

  it("setToken / getToken round-trip", () => {
    setToken("test-jwt-123");
    expect(getToken()).toBe("test-jwt-123");
  });

  it("clearToken removes the token", () => {
    setToken("test-jwt-123");
    expect(getToken()).toBe("test-jwt-123");
    clearToken();
    expect(getToken()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// useAuth hook tests
// ---------------------------------------------------------------------------

describe("useAuth", () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("returns loading=false with null user when no token is stored", async () => {
    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
  });

  it("fetches user from /v1/auth/me when token exists", async () => {
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

    setToken("valid-token");

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toEqual(mockUser);
    expect(result.current.token).toBe("valid-token");
  });

  it("clears token and returns null user on a genuine 401 from /v1/auth/me", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ error: "unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    setToken("expired-token");

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(getToken()).toBeNull(); // localStorage cleared
  });

  // Regression: UAT gap G-07-4 — a transient /v1/auth/me failure (5xx,
  // network error) must NOT wipe a valid token. The hook retries once
  // after a short delay before giving up.
  it("keeps the token when /v1/auth/me fails with a 500 twice (initial + retry)", async () => {
    const serverErrorResponse = () =>
      new Response(JSON.stringify({ error: "server_error", message: "boom" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });

    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(serverErrorResponse())
      .mockResolvedValueOnce(serverErrorResponse());

    setToken("valid-token");

    const { result } = renderHook(() => useAuth());

    await waitFor(
      () => {
        expect(result.current.loading).toBe(false);
      },
      { timeout: 3000 },
    );

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBe("valid-token");
    expect(getToken()).toBe("valid-token"); // localStorage NOT cleared
  });

  it("logs in on retry when the first /v1/auth/me call fails transiently", async () => {
    const mockUser = {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
      display_name: "Test User",
      role: "user",
      email_verified: true,
    };

    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: "server_error", message: "boom" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(mockUser), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    setToken("valid-token");

    const { result } = renderHook(() => useAuth());

    await waitFor(
      () => {
        expect(result.current.loading).toBe(false);
      },
      { timeout: 3000 },
    );

    expect(result.current.user).toEqual(mockUser);
    expect(result.current.token).toBe("valid-token");
    expect(getToken()).toBe("valid-token");
  });

  it("keeps the token when /v1/auth/me fails with a network error twice", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"));

    setToken("valid-token");

    const { result } = renderHook(() => useAuth());

    await waitFor(
      () => {
        expect(result.current.loading).toBe(false);
      },
      { timeout: 3000 },
    );

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBe("valid-token");
    expect(getToken()).toBe("valid-token"); // localStorage NOT cleared
  });

  it("logout clears user and token", async () => {
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

    setToken("valid-token");

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toEqual(mockUser);

    act(() => {
      result.current.logout();
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(getToken()).toBeNull();
  });
});
