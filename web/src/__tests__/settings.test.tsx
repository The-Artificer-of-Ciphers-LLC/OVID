import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SettingsPage from "@/app/settings/page";
import { getProviders, unlinkProvider, linkProvider, ApiError } from "@/lib/api";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mutable per-test query-param bag driving the Suspense-wrapped useSearchParams
// mock (mirrors the SearchForm.tsx idiom this page reuses for the D-05 banner).
let mockSearchParamsData: Record<string, string> = {};

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({
    get: (key: string) => mockSearchParamsData[key] ?? null,
  }),
}));

const mockUseAuth = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/lib/api", () => ({
  getProviders: vi.fn(),
  unlinkProvider: vi.fn(),
  linkProvider: vi.fn(),
  getBaseUrl: () => "http://localhost:8000",
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    constructor(status: number, code: string, message: string) {
      super(message);
      this.status = status;
      this.code = code;
    }
  },
}));

// jsdom doesn't implement real navigation — stub window.location.assign so the
// add-provider CTA's top-level-navigate step is observable without throwing.
const assignMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  mockSearchParamsData = {};

  mockUseAuth.mockReturnValue({
    user: {
      id: "u1",
      username: "testuser",
      display_name: "Test User",
      role: "user",
      email: "test@example.com",
      email_verified: true,
    },
    token: "test-token",
    loading: false,
    logout: vi.fn(),
  });

  vi.mocked(getProviders).mockResolvedValue({ providers: ["github"] });

  Object.defineProperty(window, "location", {
    value: { ...window.location, assign: assignMock },
    writable: true,
    configurable: true,
  });
});

// ---------------------------------------------------------------------------
// Unlink + min-one guard
// ---------------------------------------------------------------------------

describe("SettingsPage — unlink + min-one guard", () => {
  it("disables the last remaining unlink control", async () => {
    vi.mocked(getProviders).mockResolvedValue({ providers: ["github"] });

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("provider-github")).toBeTruthy();
    });

    expect(screen.getByTestId("unlink-github")).toBeDisabled();
  });

  it("calls unlinkProvider and refetches providers on click", async () => {
    vi.mocked(getProviders).mockResolvedValue({ providers: ["github", "google"] });
    vi.mocked(unlinkProvider).mockResolvedValueOnce({ status: "unlinked", provider: "google" });

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("provider-google")).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId("unlink-google"));

    await waitFor(() => {
      expect(unlinkProvider).toHaveBeenCalledWith("google", "test-token");
    });
    await waitFor(() => {
      expect(getProviders).toHaveBeenCalledTimes(2);
    });
  });

  it("shows the UI-SPEC copy when unlink returns 400 cannot_unlink_last", async () => {
    vi.mocked(getProviders).mockResolvedValue({ providers: ["github", "google"] });
    vi.mocked(unlinkProvider).mockRejectedValueOnce(
      new ApiError(400, "cannot_unlink_last", "Cannot unlink the only remaining provider"),
    );

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("provider-google")).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId("unlink-google"));

    await waitFor(() => {
      expect(
        screen.getByText(
          "You must keep at least one login method. Link another provider before removing this one.",
        ),
      ).toBeTruthy();
    });
  });
});

// ---------------------------------------------------------------------------
// Add-provider CTA (WEBUI-04 add path)
// ---------------------------------------------------------------------------

describe("SettingsPage — add-provider CTA", () => {
  it("renders a 'Link a provider' CTA for each not-yet-linked provider, and none for github", async () => {
    vi.mocked(getProviders).mockResolvedValue({ providers: ["github"] });

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("provider-github")).toBeTruthy();
    });

    expect(screen.getByTestId("link-google")).toBeTruthy();
    expect(screen.getByTestId("link-apple")).toBeTruthy();
    expect(screen.queryByTestId("link-github")).toBeNull();
    expect(screen.getByTestId("link-google").textContent).toContain("Link a provider");
  });

  it("initiates the add-flow via the linkProvider helper and navigates to the returned URL", async () => {
    vi.mocked(getProviders).mockResolvedValue({ providers: ["github"] });
    vi.mocked(linkProvider).mockResolvedValueOnce(
      "http://localhost:8000/v1/auth/google/login?web_redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Fcallback",
    );

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("link-google")).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId("link-google"));

    await waitFor(() => {
      expect(linkProvider).toHaveBeenCalledWith("google", "test-token");
    });
    await waitFor(() => {
      expect(assignMock).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/google/login?web_redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Fcallback",
      );
    });
  });

  it("surfaces an error and re-enables the CTA when linkProvider rejects", async () => {
    vi.mocked(getProviders).mockResolvedValue({ providers: ["github"] });
    vi.mocked(linkProvider).mockRejectedValueOnce(
      new ApiError(401, "unauthorized", "Failed to start linking provider."),
    );

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("link-google")).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId("link-google"));

    await waitFor(() => {
      expect(screen.getByText("Failed to start linking provider.")).toBeTruthy();
    });
    expect(assignMock).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// D-05 enumeration-safe merge banner
// ---------------------------------------------------------------------------

describe("SettingsPage — enumeration-safe merge banner (D-05, ME-02)", () => {
  it("renders no banner when there is no ?error param", async () => {
    vi.mocked(getProviders).mockResolvedValue({ providers: ["github"] });

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("provider-github")).toBeTruthy();
    });

    expect(screen.queryByTestId("merge-banner")).toBeNull();
  });

  it("renders an enumeration-safe role=alert aria-live=polite banner naming only current-account providers on ?error=email_conflict", async () => {
    mockSearchParamsData = { error: "email_conflict", pending_link_id: "plid-123" };
    vi.mocked(getProviders).mockResolvedValue({ providers: ["github", "google"] });

    render(<SettingsPage />);

    const banner = await screen.findByTestId("merge-banner");

    expect(banner.getAttribute("role")).toBe("alert");
    expect(banner.getAttribute("aria-live")).toBe("polite");
    expect(banner.textContent).toContain("GitHub");
    expect(banner.textContent).toContain("Google");

    // ME-02: never reveal the matched/different account, its email, or its id —
    // the banner may only ever contain the current account's own provider names.
    expect(banner.textContent).not.toMatch(/@/);
    expect(banner.textContent?.toLowerCase()).not.toContain("existing_user_id");
    expect(banner.textContent?.toLowerCase()).not.toContain("test@example.com");

    const reauthLink = screen.getByTestId("merge-banner-reauth-link");
    expect(reauthLink.getAttribute("href")).toContain("/v1/auth/github/login");
    expect(reauthLink.getAttribute("href")).toContain("pending_link_id=plid-123");
    expect(reauthLink.getAttribute("href")).not.toContain("existing_user_id");
    expect(reauthLink.getAttribute("href")).not.toMatch(/token=/);
  });
});
