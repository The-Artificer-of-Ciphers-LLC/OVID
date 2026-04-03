import { searchReleases } from "@/lib/api";
import SearchForm from "@/components/SearchForm";
import DiscCard from "@/components/DiscCard";
import Link from "next/link";

interface HomePageProps {
  searchParams: Promise<{ q?: string; year?: string; page?: string }>;
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const params = await searchParams;
  const q = params.q?.trim();
  const yearNum = params.year ? parseInt(params.year, 10) : undefined;
  const page = params.page ? parseInt(params.page, 10) : 1;

  let searchResult = null;
  let searchError: string | null = null;

  if (q) {
    try {
      searchResult = await searchReleases(
        q,
        undefined,
        Number.isFinite(yearNum) ? yearNum : undefined,
        page,
      );
    } catch (err) {
      searchError =
        err instanceof Error ? err.message : "An error occurred while searching.";
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      {/* Header */}
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-bold tracking-tight">
          <span className="text-blue-600">◉</span> OVID
        </h1>
        <p className="mt-2 text-neutral-500">
          Search the Open Video Identification Database
        </p>
      </div>

      {/* Search form */}
      <div className="mb-8">
        <SearchForm />
      </div>

      {/* Results */}
      {searchError && (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          {searchError}
        </div>
      )}

      {searchResult && (
        <>
          <p className="mb-4 text-sm text-neutral-500">
            {searchResult.total_results}{" "}
            {searchResult.total_results === 1 ? "result" : "results"} for{" "}
            <strong>&ldquo;{q}&rdquo;</strong>
            {yearNum ? ` (${yearNum})` : ""}
          </p>

          {searchResult.results.length === 0 ? (
            <p className="text-neutral-500">No releases found.</p>
          ) : (
            <div className="grid gap-3">
              {searchResult.results.map((release) => (
                <DiscCard key={release.id} release={release} />
              ))}
            </div>
          )}

          {/* Pagination */}
          {searchResult.total_pages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-4 text-sm">
              {page > 1 && (
                <Link
                  href={`/?q=${encodeURIComponent(q!)}&${yearNum ? `year=${yearNum}&` : ""}page=${page - 1}`}
                  className="rounded border border-neutral-300 px-3 py-1 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                >
                  ← Previous
                </Link>
              )}
              <span className="text-neutral-500">
                Page {page} of {searchResult.total_pages}
              </span>
              {page < searchResult.total_pages && (
                <Link
                  href={`/?q=${encodeURIComponent(q!)}&${yearNum ? `year=${yearNum}&` : ""}page=${page + 1}`}
                  className="rounded border border-neutral-300 px-3 py-1 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                >
                  Next →
                </Link>
              )}
            </div>
          )}
        </>
      )}

      {/* Empty state — no search yet */}
      {!q && (
        <p className="text-center text-neutral-400 text-sm">
          Enter a title to search the database.
        </p>
      )}
    </div>
  );
}
