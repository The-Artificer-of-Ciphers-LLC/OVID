"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

function SearchFormInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [year, setYear] = useState(searchParams.get("year") ?? "");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    const params = new URLSearchParams({ q: trimmed });
    if (year.trim()) params.set("year", year.trim());
    router.push(`/?${params.toString()}`);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
      <div className="flex-1 min-w-[200px]">
        <label htmlFor="search-query" className="block text-sm font-medium mb-1">
          Title
        </label>
        <input
          id="search-query"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search for a movie or show…"
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-neutral-700 dark:bg-neutral-900"
        />
      </div>

      <div className="w-28">
        <label htmlFor="search-year" className="block text-sm font-medium mb-1">
          Year
        </label>
        <input
          id="search-year"
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={4}
          value={year}
          onChange={(e) => setYear(e.target.value)}
          placeholder="e.g. 2024"
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-neutral-700 dark:bg-neutral-900"
        />
      </div>

      <button
        type="submit"
        className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
      >
        Search
      </button>
    </form>
  );
}

export default function SearchForm() {
  return (
    <Suspense fallback={<div className="h-12" />}>
      <SearchFormInner />
    </Suspense>
  );
}
