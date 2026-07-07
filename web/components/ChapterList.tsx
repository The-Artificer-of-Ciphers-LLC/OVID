"use client";

import { useState } from "react";
import type { ChapterResponse } from "@/lib/api";

// ---------------------------------------------------------------------------
// Time formatter
// ---------------------------------------------------------------------------

function formatTime(secs: number | null): string {
  if (secs == null) return "\u2014";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ChapterListProps {
  chapters: ChapterResponse[];
  titleIndex: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ChapterList({ chapters, titleIndex }: ChapterListProps) {
  const [expanded, setExpanded] = useState(false);

  if (!chapters || chapters.length === 0) {
    return <span>{"\u2014"}</span>;
  }

  const label = chapters.length === 1 ? "chapter" : "chapters";

  return (
    <div>
      <button
        type="button"
        className="text-sm text-blue-600 hover:underline cursor-pointer inline-flex items-center gap-1 outline-none rounded focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-neutral-950"
        aria-expanded={expanded}
        aria-controls={`chapter-table-${titleIndex}`}
        data-testid={`chapter-toggle-${titleIndex}`}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <span>{expanded ? "\u25BC" : "\u25B6"}</span>
        {chapters.length} {label}
      </button>
      {expanded && (
        <table
          id={`chapter-table-${titleIndex}`}
          data-testid={`chapter-table-${titleIndex}`}
          className="ml-8 mt-2 mb-2 text-sm"
        >
          <thead>
            <tr>
              <th className="text-left pr-3">#</th>
              <th className="text-left pr-3">Name</th>
              <th className="text-left">Start</th>
            </tr>
          </thead>
          <tbody>
            {chapters.map((ch) => (
              <tr
                key={ch.chapter_index}
                data-testid={`chapter-row-${titleIndex}-${ch.chapter_index}`}
              >
                <td className="tabular-nums text-neutral-500 pr-3 w-8">
                  {ch.chapter_index}
                </td>
                <td className="pr-3">{ch.name ?? "\u2014"}</td>
                <td className="tabular-nums text-neutral-400">
                  {formatTime(ch.start_time_secs)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
