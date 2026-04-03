import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SubmitForm from "@/components/SubmitForm";
import ProviderList from "@/components/ProviderList";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// Mock auth hook
const mockUseAuth = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock api
vi.mock("@/lib/api", () => ({
  submitDisc: vi.fn(),
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockFile(content: string, name = "disc.json"): File {
  return new File([content], name, { type: "application/json" });
}

const validFingerprint = JSON.stringify({
  fingerprint: "abc123def456",
  format: "Blu-ray",
  structure: {
    playlists: [{ id: 1 }, { id: 2 }, { id: 3 }],
  },
});

const invalidFingerprint = JSON.stringify({
  something: "else",
});

// ---------------------------------------------------------------------------
// SubmitForm tests
// ---------------------------------------------------------------------------

describe("SubmitForm", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: { id: "u1", username: "testuser", display_name: "Test", role: "user", email: "test@example.com", email_verified: true },
      token: "test-token",
      loading: false,
      logout: vi.fn(),
    });
  });

  it("renders the file input", () => {
    render(<SubmitForm />);
    expect(screen.getByTestId("fp-file-input")).toBeTruthy();
  });

  it("parses valid fingerprint JSON and shows preview", async () => {
    render(<SubmitForm />);

    const input = screen.getByTestId("fp-file-input");
    const file = createMockFile(validFingerprint);

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId("fp-preview")).toBeTruthy();
    });

    expect(screen.getByText("abc123def456")).toBeTruthy();
    expect(screen.getByText("Blu-ray")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy(); // title count from playlists
  });

  it("shows error for invalid JSON content", async () => {
    render(<SubmitForm />);

    const input = screen.getByTestId("fp-file-input");
    const file = createMockFile("not json at all");

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId("parse-error")).toBeTruthy();
    });

    expect(screen.getByTestId("parse-error").textContent).toContain(
      "Failed to parse JSON",
    );
  });

  it("shows error when fingerprint/format fields are missing", async () => {
    render(<SubmitForm />);

    const input = screen.getByTestId("fp-file-input");
    const file = createMockFile(invalidFingerprint);

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId("parse-error")).toBeTruthy();
    });

    expect(screen.getByTestId("parse-error").textContent).toContain(
      "missing 'fingerprint' or 'format'",
    );
  });

  it("renders release metadata form fields after valid file upload", async () => {
    render(<SubmitForm />);

    const input = screen.getByTestId("fp-file-input");
    fireEvent.change(input, {
      target: { files: [createMockFile(validFingerprint)] },
    });

    await waitFor(() => {
      expect(screen.getByTestId("fp-preview")).toBeTruthy();
    });

    // Check that form fields appear
    expect(screen.getByLabelText(/Release Title/)).toBeTruthy();
    expect(screen.getByLabelText(/Year/)).toBeTruthy();
    expect(screen.getByLabelText(/Content Type/)).toBeTruthy();
    expect(screen.getByLabelText(/Edition Name/)).toBeTruthy();
    expect(screen.getByLabelText(/Disc Number/)).toBeTruthy();
    expect(screen.getByLabelText(/Total Discs/)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// ProviderList tests
// ---------------------------------------------------------------------------

describe("ProviderList", () => {
  it("renders all providers", () => {
    const onUnlink = vi.fn();
    render(
      <ProviderList
        providers={["github", "google"]}
        onUnlink={onUnlink}
      />,
    );
    expect(screen.getByTestId("provider-github")).toBeTruthy();
    expect(screen.getByTestId("provider-google")).toBeTruthy();
    expect(screen.getByText("GitHub")).toBeTruthy();
    expect(screen.getByText("Google")).toBeTruthy();
  });

  it("disables Unlink button when only one provider is linked", () => {
    const onUnlink = vi.fn();
    render(
      <ProviderList
        providers={["github"]}
        onUnlink={onUnlink}
      />,
    );
    const btn = screen.getByTestId("unlink-github");
    expect(btn).toBeDisabled();
  });

  it("enables Unlink buttons when multiple providers are linked", () => {
    const onUnlink = vi.fn();
    render(
      <ProviderList
        providers={["github", "google"]}
        onUnlink={onUnlink}
      />,
    );
    const githubBtn = screen.getByTestId("unlink-github");
    const googleBtn = screen.getByTestId("unlink-google");
    expect(githubBtn).not.toBeDisabled();
    expect(googleBtn).not.toBeDisabled();
  });

  it("calls onUnlink when Unlink button is clicked", () => {
    const onUnlink = vi.fn();
    render(
      <ProviderList
        providers={["github", "google"]}
        onUnlink={onUnlink}
      />,
    );
    fireEvent.click(screen.getByTestId("unlink-github"));
    expect(onUnlink).toHaveBeenCalledWith("github");
  });

  it("shows empty state when no providers", () => {
    const onUnlink = vi.fn();
    render(<ProviderList providers={[]} onUnlink={onUnlink} />);
    expect(screen.getByTestId("no-providers")).toBeTruthy();
  });
});
