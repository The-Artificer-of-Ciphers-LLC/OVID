import type { SearchResultRelease } from "@/lib/api";

const TYPE_COLORS: Record<string, string> = {
  movie: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  tv: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
  documentary: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
};

export default function DiscCard({ release }: { release: SearchResultRelease }) {
  const badgeColor =
    TYPE_COLORS[release.content_type.toLowerCase()] ??
    "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300";

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-950">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold truncate" data-testid="disc-card-title">
            {release.title}
          </h3>
          <p className="text-sm text-neutral-500 mt-0.5">
            {release.year ? release.year : "Unknown year"}
            {" · "}
            {release.disc_count} {release.disc_count === 1 ? "disc" : "discs"}
          </p>
        </div>

        <span
          className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${badgeColor}`}
          data-testid="disc-card-type"
        >
          {release.content_type}
        </span>
      </div>
    </div>
  );
}
