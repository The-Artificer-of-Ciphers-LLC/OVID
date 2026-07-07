import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import SiblingDiscs from "@/components/SiblingDiscs";
import ChapterList from "@/components/ChapterList";
import type { SiblingDiscSummary, ChapterResponse, DiscLookupResponse } from "@/lib/api";

// ---------------------------------------------------------------------------
// Mock @/lib/api for DiscDetailPage (server component) tests
// ---------------------------------------------------------------------------

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getDisc: vi.fn(),
    getDiscEdits: vi.fn(),
  };
});

import DiscDetailPage from "@/app/disc/[fingerprint]/page";
import { getDisc, getDiscEdits } from "@/lib/api";

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const siblings: SiblingDiscSummary[] = [
  {
    fingerprint: "fp-disc-1",
    disc_number: 1,
    format: "Blu-ray",
    main_title: "The Fellowship of the Ring",
    duration_secs: 8160,
    track_count: 12,
  },
  {
    fingerprint: "fp-disc-2",
    disc_number: 2,
    format: "Blu-ray",
    main_title: "The Two Towers",
    duration_secs: 7920,
    track_count: 10,
  },
];

// ---------------------------------------------------------------------------
// SiblingDiscs
// ---------------------------------------------------------------------------

describe("SiblingDiscs", () => {
  it("renders section with data-testid sibling-discs", () => {
    render(
      <SiblingDiscs
        editionName="Extended Edition"
        discNumber={1}
        totalDiscs={3}
        siblings={siblings}
        currentFingerprint="fp-disc-1"
      />,
    );
    expect(screen.getByTestId("sibling-discs")).toBeTruthy();
  });

  it("renders heading with edition name", () => {
    render(
      <SiblingDiscs
        editionName="Extended Edition"
        discNumber={1}
        totalDiscs={3}
        siblings={siblings}
        currentFingerprint="fp-disc-1"
      />,
    );
    expect(screen.getByText("Part of: Extended Edition (Disc 1 of 3)")).toBeTruthy();
  });

  it("renders heading without edition name", () => {
    render(
      <SiblingDiscs
        editionName={null}
        discNumber={2}
        totalDiscs={3}
        siblings={siblings}
        currentFingerprint="fp-disc-2"
      />,
    );
    expect(screen.getByText("Part of a 3-disc set (Disc 2 of 3)")).toBeTruthy();
  });

  it("renders sibling cards with correct data-testid", () => {
    render(
      <SiblingDiscs
        editionName="Extended Edition"
        discNumber={1}
        totalDiscs={3}
        siblings={siblings}
        currentFingerprint="fp-disc-1"
      />,
    );
    // Disc 1 is current, disc 2 is a sibling link
    expect(screen.getByTestId("sibling-card-current")).toBeTruthy();
    expect(screen.getByTestId("sibling-card-2")).toBeTruthy();
  });

  it("marks current disc with aria-current", () => {
    render(
      <SiblingDiscs
        editionName="Extended Edition"
        discNumber={1}
        totalDiscs={3}
        siblings={siblings}
        currentFingerprint="fp-disc-1"
      />,
    );
    const current = screen.getByTestId("sibling-card-current");
    expect(current.getAttribute("aria-current")).toBe("true");
  });

  it("renders empty slots for missing disc numbers", () => {
    render(
      <SiblingDiscs
        editionName="Extended Edition"
        discNumber={1}
        totalDiscs={3}
        siblings={siblings}
        currentFingerprint="fp-disc-1"
      />,
    );
    // Disc 3 is not in siblings, should be empty slot
    const emptySlot = screen.getByTestId("sibling-card-empty-3");
    expect(emptySlot).toBeTruthy();
    expect(emptySlot.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByText("Not yet submitted")).toBeTruthy();
  });

  it("formats duration as Xh Ym on sibling cards", () => {
    render(
      <SiblingDiscs
        editionName="Extended Edition"
        discNumber={1}
        totalDiscs={3}
        siblings={siblings}
        currentFingerprint="fp-disc-1"
      />,
    );
    // Current disc (1) shows "This disc", not duration
    // Sibling disc 2: 7920 secs = 2h 12m
    expect(screen.getByText("2h 12m")).toBeTruthy();
  });

  it("renders format badge on sibling cards", () => {
    render(
      <SiblingDiscs
        editionName="Extended Edition"
        discNumber={1}
        totalDiscs={3}
        siblings={siblings}
        currentFingerprint="fp-disc-1"
      />,
    );
    // Current disc shows "Current" badge, sibling shows format badge
    expect(screen.getByText("Current")).toBeTruthy();
    const badges = screen.getAllByText("Blu-ray");
    expect(badges.length).toBe(1);
  });

  it("renders track count on sibling cards", () => {
    render(
      <SiblingDiscs
        editionName="Extended Edition"
        discNumber={1}
        totalDiscs={3}
        siblings={siblings}
        currentFingerprint="fp-disc-1"
      />,
    );
    // Only sibling disc 2 shows track count (current disc shows "This disc")
    expect(screen.getByText("10 tracks")).toBeTruthy();
  });

  it("renders main title or Untitled fallback", () => {
    const noTitleSibling: SiblingDiscSummary = {
      fingerprint: "fp-disc-x",
      disc_number: 2,
      format: "DVD",
      main_title: null,
      duration_secs: null,
      track_count: null,
    };
    render(
      <SiblingDiscs
        editionName={null}
        discNumber={1}
        totalDiscs={2}
        siblings={[noTitleSibling]}
        currentFingerprint="fp-current"
      />,
    );
    expect(screen.getByText("Untitled")).toBeTruthy();
  });

  it("applies blue border classes to current disc card", () => {
    render(
      <SiblingDiscs
        editionName="Extended Edition"
        discNumber={1}
        totalDiscs={2}
        siblings={siblings}
        currentFingerprint="fp-disc-1"
      />,
    );
    const current = screen.getByTestId("sibling-card-current");
    expect(current.className).toContain("border-blue-500");
    expect(current.className).toContain("bg-blue-50");
  });
});

// ---------------------------------------------------------------------------
// ChapterList
// ---------------------------------------------------------------------------

const chaptersData: ChapterResponse[] = [
  { chapter_index: 1, name: "Opening", start_time_secs: 0 },
  { chapter_index: 2, name: "The Journey Begins", start_time_secs: 300 },
  { chapter_index: 3, name: null, start_time_secs: 3661 },
];

describe("ChapterList", () => {
  it("shows chapter toggle when title has chapters", () => {
    render(<ChapterList chapters={chaptersData} titleIndex={1} />);
    const toggle = screen.getByTestId("chapter-toggle-1");
    expect(toggle).toBeTruthy();
    expect(toggle.textContent).toContain("3 chapters");
  });

  it("shows em-dash when title has no chapters", () => {
    const { container } = render(<ChapterList chapters={[]} titleIndex={1} />);
    expect(container.textContent).toBe("\u2014");
    expect(screen.queryByTestId("chapter-toggle-1")).toBeNull();
  });

  it("expands chapter list on toggle click", () => {
    render(<ChapterList chapters={chaptersData} titleIndex={1} />);
    expect(screen.queryByTestId("chapter-table-1")).toBeNull();

    fireEvent.click(screen.getByTestId("chapter-toggle-1"));

    expect(screen.getByTestId("chapter-table-1")).toBeTruthy();
    expect(screen.getByTestId("chapter-row-1-1")).toBeTruthy();
    expect(screen.getByTestId("chapter-row-1-2")).toBeTruthy();
    expect(screen.getByTestId("chapter-row-1-3")).toBeTruthy();
  });

  it("displays formatted chapter start times", () => {
    render(<ChapterList chapters={chaptersData} titleIndex={1} />);
    fireEvent.click(screen.getByTestId("chapter-toggle-1"));

    // 3661 seconds = 1:01:01
    expect(screen.getByText("1:01:01")).toBeTruthy();
    // 300 seconds = 5:00
    expect(screen.getByText("5:00")).toBeTruthy();
  });

  it("displays em-dash for null chapter name", () => {
    render(<ChapterList chapters={chaptersData} titleIndex={1} />);
    fireEvent.click(screen.getByTestId("chapter-toggle-1"));

    // Chapter 3 has name=null, should show em-dash
    const row3 = screen.getByTestId("chapter-row-1-3");
    const cells = row3.querySelectorAll("td");
    // Name is the second cell
    expect(cells[1].textContent).toBe("\u2014");
  });

  it("uses singular 'chapter' for single chapter", () => {
    const single: ChapterResponse[] = [
      { chapter_index: 1, name: "Intro", start_time_secs: 0 },
    ];
    render(<ChapterList chapters={single} titleIndex={2} />);
    const toggle = screen.getByTestId("chapter-toggle-2");
    expect(toggle.textContent).toContain("1 chapter");
    expect(toggle.textContent).not.toContain("chapters");
  });
});

// ---------------------------------------------------------------------------
// DiscDetailPage — fingerprint aliases + unverified-withheld message (WEBUI-02)
// ---------------------------------------------------------------------------

function makeDisc(overrides: Partial<DiscLookupResponse> = {}): DiscLookupResponse {
  return {
    request_id: "req-1",
    fingerprint: "dvd1-primary123",
    format: "DVD",
    status: "verified",
    confidence: "high",
    region_code: null,
    upc: null,
    edition_name: null,
    disc_number: 1,
    total_discs: 1,
    submitted_by: null,
    verified_by: null,
    release: {
      title: "Test Movie",
      year: 2020,
      content_type: "movie",
      tmdb_id: null,
      imdb_id: null,
    },
    titles: [],
    fingerprint_aliases: [],
    disc_set: null,
    ...overrides,
  };
}

async function renderDiscDetail(disc: DiscLookupResponse) {
  vi.mocked(getDisc).mockResolvedValue(disc);
  vi.mocked(getDiscEdits).mockResolvedValue({
    request_id: "req-1",
    fingerprint: disc.fingerprint,
    edits: [],
  });
  const element = await DiscDetailPage({
    params: Promise.resolve({ fingerprint: disc.fingerprint }),
  });
  return render(element);
}

describe("DiscDetailPage — fingerprint aliases (WEBUI-02)", () => {
  it("renders the fingerprint-aliases section with all identity strings and the primary badge", async () => {
    const disc = makeDisc({
      fingerprint_aliases: [
        { fingerprint: "dvd1-primary123", method: "dvd1", is_primary: true },
        { fingerprint: "dvdread1-secondary456", method: "dvdread1", is_primary: false },
      ],
    });
    await renderDiscDetail(disc);

    const section = screen.getByTestId("fingerprint-aliases");
    expect(section).toBeTruthy();
    expect(within(section).getByText("dvd1-primary123")).toBeTruthy();
    expect(within(section).getByText("dvdread1-secondary456")).toBeTruthy();
    expect(within(section).getByText("primary")).toBeTruthy();
  });

  it("shows the no-aliases empty copy when there are no additional aliases", async () => {
    const disc = makeDisc({ fingerprint_aliases: [] });
    await renderDiscDetail(disc);

    expect(screen.getByText("No additional fingerprint aliases recorded.")).toBeTruthy();
  });

  it("shows the unverified-withheld message instead of a titles table when status is unverified", async () => {
    const disc = makeDisc({ status: "unverified", titles: [] });
    await renderDiscDetail(disc);

    expect(
      screen.getByText("Structure withheld until a second contributor verifies this disc."),
    ).toBeTruthy();
    expect(screen.queryByTestId("title-row")).toBeNull();
  });
});

describe("DiscDetailPage — alias completeness + withheld edge cases (WEBUI-02 gap closure)", () => {
  it("renders every provided alias without hiding or renumbering, including dvd1- and dvdread1- identity strings", async () => {
    const disc = makeDisc({
      fingerprint_aliases: [
        { fingerprint: "dvd1-abc111", method: "dvd1", is_primary: true },
        { fingerprint: "dvdread1-def222", method: "dvdread1", is_primary: false },
        { fingerprint: "bd1-ghi333", method: "bd1", is_primary: false },
      ],
    });
    await renderDiscDetail(disc);

    const section = screen.getByTestId("fingerprint-aliases");
    const codes = Array.from(section.querySelectorAll("code")).map((el) => el.textContent);
    expect(codes).toEqual(["dvd1-abc111", "dvdread1-def222", "bd1-ghi333"]);
  });

  it("renders the primary badge on exactly the aliased entry marked is_primary", async () => {
    const disc = makeDisc({
      fingerprint_aliases: [
        { fingerprint: "dvd1-abc111", method: "dvd1", is_primary: false },
        { fingerprint: "dvdread1-def222", method: "dvdread1", is_primary: true },
      ],
    });
    await renderDiscDetail(disc);

    expect(screen.getAllByText("primary")).toHaveLength(1);
  });

  it("shows the no-aliases empty copy for a single-alias disc (boundary: length === 1)", async () => {
    const disc = makeDisc({
      fingerprint_aliases: [{ fingerprint: "dvd1-onlyone", method: "dvd1", is_primary: true }],
    });
    await renderDiscDetail(disc);

    expect(screen.getByText("No additional fingerprint aliases recorded.")).toBeTruthy();
  });

  it("does not crash and shows the empty copy when fingerprint_aliases is undefined", async () => {
    const disc = makeDisc();
    delete (disc as { fingerprint_aliases?: DiscLookupResponse["fingerprint_aliases"] }).fingerprint_aliases;
    await renderDiscDetail(disc);

    expect(screen.getByText("No additional fingerprint aliases recorded.")).toBeTruthy();
  });

  it("renders aliases and release info even when the disc is unverified", async () => {
    const disc = makeDisc({
      status: "unverified",
      titles: [],
      fingerprint_aliases: [
        { fingerprint: "dvd1-abc111", method: "dvd1", is_primary: true },
        { fingerprint: "dvdread1-def222", method: "dvdread1", is_primary: false },
      ],
    });
    await renderDiscDetail(disc);

    expect(screen.getByText("Test Movie")).toBeTruthy();
    expect(screen.getByText("dvd1-abc111")).toBeTruthy();
    expect(screen.getByText("dvdread1-def222")).toBeTruthy();
  });
});
