import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import SiblingDiscs from "@/components/SiblingDiscs";
import type { SiblingDiscSummary } from "@/lib/api";

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
