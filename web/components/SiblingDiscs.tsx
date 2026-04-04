// SiblingDiscs -- horizontal card row showing sibling discs in a multi-disc set.

import Link from "next/link";
import type { SiblingDiscSummary } from "@/lib/api";

// ---------------------------------------------------------------------------
// Format badge colors (per UI-SPEC)
// ---------------------------------------------------------------------------

const FORMAT_COLORS: Record<string, string> = {
  dvd: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  "blu-ray": "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  uhd: "bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-200",
};

// ---------------------------------------------------------------------------
// Duration formatter
// ---------------------------------------------------------------------------

function _formatDuration(secs: number): string {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return `${h}h ${m}m`;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SiblingDiscsProps {
  editionName: string | null;
  discNumber: number;
  totalDiscs: number;
  siblings: SiblingDiscSummary[];
  currentFingerprint: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SiblingDiscs({
  editionName,
  discNumber,
  totalDiscs,
  siblings,
  currentFingerprint,
}: SiblingDiscsProps) {
  // Build a map of disc_number -> sibling for quick lookup
  const siblingByNumber = new Map<number, SiblingDiscSummary>();
  for (const s of siblings) {
    siblingByNumber.set(s.disc_number, s);
  }

  // Build all slot numbers from 1 to totalDiscs
  const slots = Array.from({ length: totalDiscs }, (_, i) => i + 1);

  const heading = editionName
    ? `Part of: ${editionName} (Disc ${discNumber} of ${totalDiscs})`
    : `Part of a ${totalDiscs}-disc set (Disc ${discNumber} of ${totalDiscs})`;

  return (
    <section className="mb-8" data-testid="sibling-discs">
      <h2 className="text-sm font-bold mb-3">{heading}</h2>
      <div className="flex flex-wrap gap-4">
        {slots.map((slotNum) => {
          const sibling = siblingByNumber.get(slotNum);
          const isCurrent = sibling?.fingerprint === currentFingerprint;

          // Empty slot -- disc not yet submitted
          if (!sibling) {
            return (
              <div
                key={slotNum}
                className="rounded-lg border border-dashed border-neutral-300 bg-transparent p-4 min-w-[180px] max-w-[220px] dark:border-neutral-700"
                aria-disabled="true"
                data-testid={`sibling-card-empty-${slotNum}`}
              >
                <p className="text-xs font-normal text-neutral-400">Disc {slotNum}</p>
                <p className="text-sm text-neutral-400 mt-1">Not yet submitted</p>
              </div>
            );
          }

          const formatKey = sibling.format.toLowerCase();
          const badgeColor =
            FORMAT_COLORS[formatKey] ??
            "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300";

          const cardContent = (
            <>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-normal text-neutral-500">Disc {sibling.disc_number}</span>
                <span className={`text-xs rounded px-2 py-1 ${badgeColor}`}>
                  {sibling.format}
                </span>
              </div>
              <p className="text-sm font-bold truncate">{sibling.main_title ?? "Untitled"}</p>
              {sibling.duration_secs != null && (
                <p className="text-xs text-neutral-400">{_formatDuration(sibling.duration_secs)}</p>
              )}
              {sibling.track_count != null && (
                <p className="text-xs text-neutral-400">{sibling.track_count} tracks</p>
              )}
            </>
          );

          if (isCurrent) {
            return (
              <div
                key={slotNum}
                className="rounded-lg border border-blue-500 bg-blue-50 p-4 min-w-[180px] max-w-[220px] dark:border-blue-400 dark:bg-blue-950"
                aria-current="true"
                data-testid="sibling-card-current"
              >
                {cardContent}
              </div>
            );
          }

          return (
            <Link
              key={slotNum}
              href={`/disc/${sibling.fingerprint}`}
              aria-label={`View Disc ${sibling.disc_number}: ${sibling.main_title ?? "Untitled"}`}
              className="rounded-lg border border-neutral-200 bg-neutral-50 p-4 min-w-[180px] max-w-[220px] hover:border-neutral-300 hover:shadow-sm transition-all dark:border-neutral-800 dark:bg-neutral-900"
              data-testid={`sibling-card-${sibling.disc_number}`}
            >
              {cardContent}
            </Link>
          );
        })}
      </div>
    </section>
  );
}
