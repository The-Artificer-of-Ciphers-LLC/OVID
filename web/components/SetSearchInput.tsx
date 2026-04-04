"use client";

// SetSearchInput -- search-as-you-type for existing disc sets with debounce.

import { useState, useEffect, useRef, useCallback } from "react";
import { searchSets, type DiscSetSearchResult } from "@/lib/api";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SetSearchInputProps {
  onSelect: (setId: string, setInfo: DiscSetSearchResult) => void;
  onCreateNew: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SetSearchInput({ onSelect, onCreateNew }: SetSearchInputProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DiscSetSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const blurTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const inputClass =
    "w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-neutral-700 dark:bg-neutral-900";

  // -------------------------------------------------------------------------
  // Debounced search
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      setShowDropdown(false);
      setLoading(false);
      return;
    }

    setLoading(true);
    setShowDropdown(true);

    const timer = setTimeout(() => {
      searchSets(query)
        .then((res) => {
          setResults(res.results);
          setLoading(false);
        })
        .catch(() => {
          setResults([]);
          setLoading(false);
        });
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  // -------------------------------------------------------------------------
  // Keyboard navigation
  // -------------------------------------------------------------------------

  // Total selectable items: results + "Create new set" row
  const totalItems = results.length + 1;

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!showDropdown) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((prev) => (prev + 1) % totalItems);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((prev) => (prev - 1 + totalItems) % totalItems);
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (activeIndex >= 0 && activeIndex < results.length) {
          const selected = results[activeIndex];
          onSelect(selected.id, selected);
          setShowDropdown(false);
          setQuery("");
        } else if (activeIndex === results.length) {
          onCreateNew();
          setShowDropdown(false);
          setQuery("");
        }
      } else if (e.key === "Escape") {
        setShowDropdown(false);
      }
    },
    [showDropdown, activeIndex, results, totalItems, onSelect, onCreateNew],
  );

  // -------------------------------------------------------------------------
  // Blur handler (delay so click on result registers)
  // -------------------------------------------------------------------------

  function handleBlur() {
    blurTimeoutRef.current = setTimeout(() => {
      setShowDropdown(false);
    }, 200);
  }

  function handleFocus() {
    if (blurTimeoutRef.current) {
      clearTimeout(blurTimeoutRef.current);
      blurTimeoutRef.current = null;
    }
    if (query.length >= 2) {
      setShowDropdown(true);
    }
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="relative">
      <input
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setActiveIndex(-1);
        }}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        onFocus={handleFocus}
        placeholder="Search sets by release title or edition..."
        className={inputClass}
        data-testid="set-search-input"
        role="combobox"
        aria-expanded={showDropdown}
        aria-haspopup="listbox"
      />

      {showDropdown && (
        <div
          className="absolute mt-1 w-full rounded-lg border border-neutral-200 bg-white shadow-lg max-h-60 overflow-y-auto z-10 dark:border-neutral-800 dark:bg-neutral-950"
          role="listbox"
          data-testid="set-search-dropdown"
        >
          {loading && (
            <div className="px-4 py-2 text-sm text-neutral-400">Searching...</div>
          )}

          {!loading && results.length === 0 && (
            <div className="px-4 py-2 text-sm text-neutral-400">No matching sets found</div>
          )}

          {!loading &&
            results.map((result, idx) => (
              <div
                key={result.id}
                role="option"
                aria-selected={idx === activeIndex}
                className={`px-4 py-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 cursor-pointer text-sm ${idx === activeIndex ? "bg-neutral-100 dark:bg-neutral-800" : ""}`}
                data-testid={`set-search-result-${result.id}`}
                onClick={() => {
                  onSelect(result.id, result);
                  setShowDropdown(false);
                  setQuery("");
                }}
              >
                {result.edition_name ?? "Unnamed set"} ({result.discs.length}/{result.total_discs} discs linked)
              </div>
            ))}

          {!loading && (
            <div
              className="px-4 py-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 cursor-pointer text-sm text-blue-600 font-normal"
              data-testid="set-search-create-new"
              role="option"
              aria-selected={activeIndex === results.length}
              onClick={() => {
                onCreateNew();
                setShowDropdown(false);
                setQuery("");
              }}
            >
              Create new set
            </div>
          )}
        </div>
      )}
    </div>
  );
}
