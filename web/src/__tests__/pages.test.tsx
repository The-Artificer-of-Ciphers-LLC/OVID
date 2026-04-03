import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import DiscCard from "@/components/DiscCard";
import DiscStructure from "@/components/DiscStructure";
import EditHistory from "@/components/EditHistory";
import type {
  SearchResultRelease,
  TitleResponse,
  DiscEditResponse,
} from "@/lib/api";

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
