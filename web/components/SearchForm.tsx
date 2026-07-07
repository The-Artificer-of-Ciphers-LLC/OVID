"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Input from "@/components/Input";

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
    <form
      onSubmit={handleSubmit}
      className="mx-auto flex w-full max-w-2xl flex-col gap-4"
    >
      <Field id="search-query" label="Title">
        <Input
          id="search-query"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search for a movie or show…"
          data-testid="search-query-input"
        />
      </Field>

      <div className="flex flex-wrap items-end gap-3">
        <div className="w-28">
          <Field id="search-year" label="Year">
            <Input
              id="search-year"
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={4}
              value={year}
              onChange={(e) => setYear(e.target.value)}
              placeholder="e.g. 2024"
              data-testid="search-year-input"
            />
          </Field>
        </div>

        <Button type="submit" data-testid="search-submit">
          Search discs
        </Button>
      </div>
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
