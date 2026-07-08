import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import AuthCallbackPage from "@/app/auth/callback/page";
import { setToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mutable per-test query-param bag driving the Suspense-wrapped useSearchParams
// mock (mirrors the SearchForm.tsx idiom reused across web/src/__tests__).
let mockSearchParamsData: Record<string, string> = {};

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: replaceMock, prefetch: vi.fn() }),
  useSearchParams: () => ({
    get: (key: string) => mockSearchParamsData[key] ?? null,
  }),
}));

vi.mock("@/lib/auth", () => ({
  setToken: vi.fn(),
}));

// jsdom's window.location.assign is a real navigation trigger and isn't
// implemented — stub it so the full-navigation regression is observable
// without throwing (mirrors settings.test.tsx).
const assignMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  mockSearchParamsData = {};

  Object.defineProperty(window, "location", {
    value: { ...window.location, assign: assignMock },
    writable: true,
    configurable: true,
  });
});

// ---------------------------------------------------------------------------
// Success path — full navigation regression (fixes stale nav state bug)
// ---------------------------------------------------------------------------

describe("AuthCallbackPage — success", () => {
  it("stores the token and performs a full navigation to / (not a client-side router.replace)", async () => {
    mockSearchParamsData = { token: "jwt.abc.def" };

    render(<AuthCallbackPage />);

    await waitFor(() => {
      expect(setToken).toHaveBeenCalledWith("jwt.abc.def");
    });
    await waitFor(() => {
      expect(assignMock).toHaveBeenCalledWith("/");
    });

    // Regression guard: this must be a full navigation, not client-side
    // routing — otherwise the auth/nav state goes stale until manual refresh.
    expect(replaceMock).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Error path
// ---------------------------------------------------------------------------

describe("AuthCallbackPage — error", () => {
  it("redirects to /settings with the error forwarded when no token is present", async () => {
    mockSearchParamsData = { error: "email_conflict", pending_link_id: "plid-123" };

    render(<AuthCallbackPage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith(
        "/settings?error=email_conflict&pending_link_id=plid-123",
      );
    });

    expect(setToken).not.toHaveBeenCalled();
    expect(assignMock).not.toHaveBeenCalled();
  });
});
