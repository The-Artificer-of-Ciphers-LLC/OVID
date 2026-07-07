"use client";

import { useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChapterCreate {
  chapter_index: number;
  name: string | null;
  start_time_secs: number | null;
}

interface ChapterEditorProps {
  titleIndex: number;
  chapters: ChapterCreate[];
  onChange: (chapters: ChapterCreate[]) => void;
}

// ---------------------------------------------------------------------------
// Time parsing
// ---------------------------------------------------------------------------

function parseTime(value: string): number | null {
  const parts = value.split(":").map((p) => parseInt(p, 10));
  if (parts.some((p) => isNaN(p))) return null;
  if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  }
  if (parts.length === 2) {
    return parts[0] * 60 + parts[1];
  }
  return null;
}

function formatTimeValue(secs: number | null): string {
  if (secs == null) return "";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Shared input class (matches project pattern)
// ---------------------------------------------------------------------------

const inputClass =
  "rounded border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-neutral-700 dark:bg-neutral-900";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ChapterEditor({
  titleIndex,
  chapters,
  onChange,
}: ChapterEditorProps) {
  const [expanded, setExpanded] = useState(false);

  function handleNameChange(index: number, value: string) {
    const updated = chapters.map((ch) =>
      ch.chapter_index === index
        ? { ...ch, name: value === "" ? null : value }
        : ch,
    );
    onChange(updated);
  }

  function handleTimeBlur(index: number, value: string) {
    const secs = value.trim() === "" ? null : parseTime(value.trim());
    const updated = chapters.map((ch) =>
      ch.chapter_index === index ? { ...ch, start_time_secs: secs } : ch,
    );
    onChange(updated);
  }

  function handleAdd() {
    const next: ChapterCreate = {
      chapter_index: chapters.length + 1,
      name: null,
      start_time_secs: null,
    };
    onChange([...chapters, next]);
  }

  function handleRemove(index: number) {
    const filtered = chapters.filter((ch) => ch.chapter_index !== index);
    // Re-index sequentially
    const reindexed = filtered.map((ch, i) => ({
      ...ch,
      chapter_index: i + 1,
    }));
    onChange(reindexed);
  }

  return (
    <div>
      <button
        type="button"
        className="text-sm text-blue-600 hover:underline cursor-pointer inline-flex items-center gap-1"
        aria-expanded={expanded}
        aria-controls={`chapter-editor-${titleIndex}`}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <span>{expanded ? "\u25BC" : "\u25B6"}</span>
        Add chapters
      </button>
      {expanded && (
        <div
          id={`chapter-editor-${titleIndex}`}
          data-testid={`chapter-editor-${titleIndex}`}
          className="mt-2"
        >
          {chapters.map((ch) => (
            <div
              key={ch.chapter_index}
              className="flex items-center gap-3 mb-2 sm:flex-row flex-col"
            >
              <span className="text-sm tabular-nums text-neutral-500 w-8 text-right">
                {ch.chapter_index}
              </span>
              <input
                type="text"
                className={`${inputClass} flex-1`}
                placeholder="Chapter name (optional)"
                maxLength={200}
                aria-label={`Name for chapter ${ch.chapter_index}`}
                data-testid={`chapter-name-${titleIndex}-${ch.chapter_index}`}
                value={ch.name ?? ""}
                onChange={(e) =>
                  handleNameChange(ch.chapter_index, e.target.value)
                }
              />
              <input
                type="text"
                inputMode="numeric"
                className={`${inputClass} w-28`}
                placeholder="0:00:00"
                aria-label={`Start time for chapter ${ch.chapter_index}`}
                data-testid={`chapter-time-${titleIndex}-${ch.chapter_index}`}
                defaultValue={formatTimeValue(ch.start_time_secs)}
                onBlur={(e) =>
                  handleTimeBlur(ch.chapter_index, e.target.value)
                }
              />
              <button
                type="button"
                className="text-neutral-400 hover:text-red-600 text-sm cursor-pointer"
                aria-label={`Remove chapter ${ch.chapter_index}`}
                data-testid={`chapter-remove-${titleIndex}-${ch.chapter_index}`}
                onClick={() => handleRemove(ch.chapter_index)}
              >
                {"\u00D7"}
              </button>
            </div>
          ))}
          <button
            type="button"
            className="text-sm text-blue-600 hover:underline cursor-pointer mt-1"
            data-testid={`chapter-add-${titleIndex}`}
            onClick={handleAdd}
          >
            Add chapter
          </button>
        </div>
      )}
    </div>
  );
}
