import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import DiscCard from "@/components/DiscCard";
import DiscStructure from "@/components/DiscStructure";
import EditHistory from "@/components/EditHistory";
import type {
  SearchResultRelease,
  TitleResponse,
  DiscEditResponse,
  SearchResponse,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Mocks for HomePage (server component) — search surface (WEBUI-01)
// ---------------------------------------------------------------------------

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    searchReleases: vi.fn(),
  };
});

import HomePage from "@/app/page";
import { searchReleases } from "@/lib/api";

// ---------------------------------------------------------------------------
// DiscCard
// ---------------------------------------------------------------------------

describe("DiscCard", () => {
  const release: SearchResultRelease = {
    id: "rel-001",
    title: "Blade Runner 2049",
    year: 2017,
    content_type: "movie",
    tmdb_id: 335984,
    disc_count: 2,
  };

  it("renders title and year", () => {
    render(<DiscCard release={release} />);
    expect(screen.getByTestId("disc-card-title")).toHaveTextContent(
      "Blade Runner 2049",
    );
    expect(screen.getByText(/2017/)).toBeTruthy();
  });

  it("renders content_type badge", () => {
    render(<DiscCard release={release} />);
    expect(screen.getByTestId("disc-card-type")).toHaveTextContent("movie");
  });

  it("renders disc count", () => {
    render(<DiscCard release={release} />);
    expect(screen.getByText(/2 discs/)).toBeTruthy();
  });

  it("shows 'Unknown year' when year is null", () => {
    render(<DiscCard release={{ ...release, year: null }} />);
    expect(screen.getByText(/Unknown year/)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// DiscStructure
// ---------------------------------------------------------------------------

describe("DiscStructure", () => {
  const titles: TitleResponse[] = [
    {
      title_index: 0,
      is_main_feature: true,
      title_type: null,
      display_name: "Main Feature",
      duration_secs: 9390, // 02:36:30
      chapter_count: 32,
      audio_tracks: [
        { index: 0, language: "en", codec: "AC3", channels: 6, is_default: true },
        { index: 1, language: "es", codec: "AC3", channels: 2, is_default: false },
      ],
      subtitle_tracks: [
        { index: 0, language: "en", codec: null, channels: null, is_default: true },
      ],
      chapters: [],
    },
    {
      title_index: 1,
      is_main_feature: false,
      title_type: null,
      display_name: null,
      duration_secs: 600, // 00:10:00
      chapter_count: 3,
      audio_tracks: [],
      subtitle_tracks: [],
      chapters: [],
    },
  ];

  it("renders the correct number of title rows", () => {
    render(<DiscStructure titles={titles} />);
    const rows = screen.getAllByTestId("title-row");
    expect(rows).toHaveLength(2);
  });

  it("renders display names and falls back to 'Title N'", () => {
    render(<DiscStructure titles={titles} />);
    expect(screen.getByText("Main Feature")).toBeTruthy();
    expect(screen.getByText("Title 1")).toBeTruthy();
  });

  it("formats duration as HH:MM:SS", () => {
    render(<DiscStructure titles={titles} />);
    expect(screen.getByText("02:36:30")).toBeTruthy();
    expect(screen.getByText("00:10:00")).toBeTruthy();
  });

  it("shows Main badge for main feature", () => {
    render(<DiscStructure titles={titles} />);
    expect(screen.getByText("Main")).toBeTruthy();
  });

  it("summarizes audio tracks", () => {
    render(<DiscStructure titles={titles} />);
    expect(screen.getByText(/EN AC3 6ch/)).toBeTruthy();
    expect(screen.getByText(/ES AC3 2ch/)).toBeTruthy();
  });

  it("renders empty state", () => {
    render(<DiscStructure titles={[]} />);
    expect(screen.getByText("No title structure available.")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// EditHistory
// ---------------------------------------------------------------------------

describe("EditHistory", () => {
  const edits: DiscEditResponse[] = [
    {
      edit_type: "create",
      field_changed: null,
      old_value: null,
      new_value: null,
      edit_note: "Initial submission",
      created_at: "2024-03-15T10:30:00Z",
      user_id: "user-1",
    },
    {
      edit_type: "update",
      field_changed: "title",
      old_value: "Bladerunner",
      new_value: "Blade Runner 2049",
      edit_note: null,
      created_at: "2024-03-16T14:22:00Z",
      user_id: "user-2",
    },
  ];

  it("renders the correct number of edit entries", () => {
    render(<EditHistory edits={edits} />);
    const entries = screen.getAllByTestId("edit-entry");
    expect(entries).toHaveLength(2);
  });

  it("renders edit type badges", () => {
    render(<EditHistory edits={edits} />);
    expect(screen.getByText("create")).toBeTruthy();
    expect(screen.getByText("update")).toBeTruthy();
  });

  it("renders old→new values for updates", () => {
    render(<EditHistory edits={edits} />);
    expect(screen.getByText("Bladerunner")).toBeTruthy();
    expect(screen.getByText(/Blade Runner 2049/)).toBeTruthy();
  });

  it("renders edit notes", () => {
    render(<EditHistory edits={edits} />);
    expect(screen.getByText("Initial submission")).toBeTruthy();
  });

  it("renders empty state", () => {
    render(<EditHistory edits={[]} />);
    expect(screen.getByText("No edit history.")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// HomePage — search surface (WEBUI-01, 07-05)
// ---------------------------------------------------------------------------

describe("HomePage", () => {
  const release: SearchResultRelease = {
    id: "rel-001",
    title: "Blade Runner 2049",
    year: 2017,
    content_type: "movie",
    tmdb_id: 335984,
    disc_count: 2,
  };

  function makeSearchResponse(
    overrides: Partial<SearchResponse> = {},
  ): SearchResponse {
    return {
      request_id: "req-1",
      results: [release],
      page: 1,
      total_pages: 1,
      total_results: 1,
      ...overrides,
    };
  }

  async function renderHomePage(params: {
    q?: string;
    year?: string;
    page?: string;
  }) {
    const element = await HomePage({ searchParams: Promise.resolve(params) });
    return render(element);
  }

  it("renders the submit CTA with the 'Search discs' label and a focus-visible ring", async () => {
    await renderHomePage({});
    const cta = screen.getByRole("button", { name: "Search discs" });
    expect(cta).toBeTruthy();
    expect(cta.className).toMatch(/focus-visible:ring/);
  });

  it("shows the no-query empty state at AA-safe contrast (not neutral-400)", async () => {
    await renderHomePage({});
    const hint = screen.getByText("Enter a title to search the database.");
    expect(hint).toBeTruthy();
    expect(hint.className).not.toMatch(/text-neutral-400/);
  });

  it("renders the results grid and count when search returns results", async () => {
    vi.mocked(searchReleases).mockResolvedValue(makeSearchResponse());
    await renderHomePage({ q: "Blade Runner" });

    expect(screen.getByTestId("disc-card-title")).toHaveTextContent(
      "Blade Runner 2049",
    );
    expect(screen.getByText(/1 result for/)).toBeTruthy();
  });

  it("renders zero-results copy with a follow-up hint", async () => {
    vi.mocked(searchReleases).mockResolvedValue(
      makeSearchResponse({ results: [], total_results: 0 }),
    );
    await renderHomePage({ q: "Nonexistent Title" });

    expect(screen.getByText("No releases found.")).toBeTruthy();
    expect(
      screen.getByText("Check the spelling or try a broader title."),
    ).toBeTruthy();
  });

  it("renders pagination controls when there are multiple result pages", async () => {
    vi.mocked(searchReleases).mockResolvedValue(
      makeSearchResponse({ page: 1, total_pages: 3, total_results: 30 }),
    );
    await renderHomePage({ q: "Blade Runner" });

    expect(screen.getByText("Page 1 of 3")).toBeTruthy();
    expect(screen.getByText("Next →")).toBeTruthy();
    expect(screen.queryByText("← Previous")).toBeNull();
  });
});
