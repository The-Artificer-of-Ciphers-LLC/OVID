"use client";

import { useState } from "react";
import Input from "@/components/Input";

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
// Shared D-03 focus-visible ring for the compact inline text buttons
// (kept as raw <button>s rather than the Button primitive to preserve their
// compact inline-link visual shape -- matches the 07-04 ChapterList precedent)
// ---------------------------------------------------------------------------

const linkButtonBaseClass =
  "rounded text-sm cursor-pointer outline-none " +
  "focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-neutral-950";

const linkButtonClass = `${linkButtonBaseClass} text-blue-600 hover:underline`;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ChapterEditor({
  titleIndex,
  chapters,
  onChange,
}: ChapterEditorProps) {
  const [expanded, setExpanded] = useState(false);
  // WR-06: per-chapter malformed-time validation error, keyed by chapter_index.
  const [timeErrors, setTimeErrors] = useState<Record<number, string>>({});

  function handleNameChange(index: number, value: string) {
    const updated = chapters.map((ch) =>
      ch.chapter_index === index
        ? { ...ch, name: value === "" ? null : value }
        : ch,
    );
    onChange(updated);
  }

  function clearTimeError(index: number) {
    setTimeErrors((prev) => {
      if (!(index in prev)) return prev;
      const next = { ...prev };
      delete next[index];
      return next;
    });
  }

  function handleTimeBlur(index: number, value: string) {
    const trimmed = value.trim();
    if (trimmed === "") {
      // Intentional clear — not a validation error.
      clearTimeError(index);
      const updated = chapters.map((ch) =>
        ch.chapter_index === index ? { ...ch, start_time_secs: null } : ch,
      );
      onChange(updated);
      return;
    }
    const secs = parseTime(trimmed);
    if (secs === null) {
      // Unparseable input (WR-06): surface an inline error and leave the
      // previously-stored value untouched rather than silently discarding it.
      setTimeErrors((prev) => ({ ...prev, [index]: "Use H:MM:SS or MM:SS" }));
      return;
    }
    clearTimeError(index);
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
        className={`${linkButtonClass} inline-flex items-center gap-1`}
        aria-expanded={expanded}
        aria-controls={`chapter-editor-${titleIndex}`}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <span>{expanded ? "▼" : "▶"}</span>
        Add chapters
      </button>
      {expanded && (
        <div
          id={`chapter-editor-${titleIndex}`}
          data-testid={`chapter-editor-${titleIndex}`}
          className="mt-2"
        >
          {chapters.map((ch) => (
            <div key={ch.chapter_index} className="mb-2">
              <div className="flex items-center gap-3 sm:flex-row flex-col">
                <span className="text-sm tabular-nums text-neutral-500 w-8 text-right">
                  {ch.chapter_index}
                </span>
                <Input
                  type="text"
                  className="flex-1"
                  placeholder="Chapter name (optional)"
                  maxLength={200}
                  aria-label={`Name for chapter ${ch.chapter_index}`}
                  data-testid={`chapter-name-${titleIndex}-${ch.chapter_index}`}
                  value={ch.name ?? ""}
                  onChange={(e) =>
                    handleNameChange(ch.chapter_index, e.target.value)
                  }
                />
                <Input
                  type="text"
                  inputMode="numeric"
                  className="w-28"
                  placeholder="0:00:00"
                  aria-label={`Start time for chapter ${ch.chapter_index}`}
                  aria-invalid={ch.chapter_index in timeErrors}
                  data-testid={`chapter-time-${titleIndex}-${ch.chapter_index}`}
                  defaultValue={formatTimeValue(ch.start_time_secs)}
                  onBlur={(e) =>
                    handleTimeBlur(ch.chapter_index, e.target.value)
                  }
                />
                <button
                  type="button"
                  className={`${linkButtonBaseClass} text-neutral-500 hover:text-red-600`}
                  aria-label={`Remove chapter ${ch.chapter_index}`}
                  data-testid={`chapter-remove-${titleIndex}-${ch.chapter_index}`}
                  onClick={() => handleRemove(ch.chapter_index)}
                >
                  {"×"}
                </button>
              </div>
              {timeErrors[ch.chapter_index] ? (
                <p
                  data-testid={`chapter-time-error-${titleIndex}-${ch.chapter_index}`}
                  aria-live="polite"
                  className="mt-1 text-sm text-red-600 dark:text-red-400 sm:ml-11"
                >
                  {timeErrors[ch.chapter_index]}
                </p>
              ) : null}
            </div>
          ))}
          <button
            type="button"
            className={`${linkButtonClass} mt-1`}
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
