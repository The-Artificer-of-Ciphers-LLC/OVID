import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getDisc, getDiscEdits, ApiError } from "@/lib/api";
import DiscStructure from "@/components/DiscStructure";
import EditHistory from "@/components/EditHistory";
import DisputeResolver from "@/components/DisputeResolver";

type Props = {
  params: Promise<{ fingerprint: string }>;
};

// ---------------------------------------------------------------------------
// Metadata (Open Graph / SEO)
// ---------------------------------------------------------------------------

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { fingerprint } = await params;

  try {
    const disc = await getDisc(fingerprint);
    const title = disc.release?.title ?? `Disc ${fingerprint}`;
    const year = disc.release?.year;
    const description = [
      disc.format,
      year ? `(${year})` : null,
      disc.region_code ? `Region ${disc.region_code}` : null,
      `${disc.titles.length} titles`,
    ]
      .filter(Boolean)
      .join(" · ");

    return {
      title: `${title} — OVID`,
      description,
      openGraph: {
        title,
        description,
        type: "website",
      },
    };
  } catch {
    return { title: "Disc not found — OVID" };
  }
}

// ---------------------------------------------------------------------------
// Status badge helper
// ---------------------------------------------------------------------------

const STATUS_STYLES: Record<string, string> = {
  verified: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  disputed: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  unverified: "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400",
};

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default async function DiscDetailPage({ params }: Props) {
  const { fingerprint } = await params;

  let disc;
  let editsResult;

  try {
    [disc, editsResult] = await Promise.all([
      getDisc(fingerprint),
      getDiscEdits(fingerprint).catch(() => null),
    ]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }

  const release = disc.release;
  const edits = editsResult?.edits ?? [];

  const statusStyle =
    STATUS_STYLES[disc.status.toLowerCase()] ?? STATUS_STYLES.unverified;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex flex-wrap items-center gap-3 mb-2">
          <h1 className="text-2xl font-bold">
            {release?.title ?? `Disc ${fingerprint}`}
          </h1>
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${statusStyle}`}>
            {disc.status}
          </span>
        </div>

        <p className="text-sm text-neutral-500">
          {disc.format}
          {release?.year ? ` · ${release.year}` : ""}
          {disc.region_code ? ` · Region ${disc.region_code}` : ""}
          {disc.edition_name ? ` · ${disc.edition_name}` : ""}
          {disc.total_discs > 1 ? ` · Disc ${disc.disc_number} of ${disc.total_discs}` : ""}
        </p>

        {/* External links */}
        {release && (release.tmdb_id || release.imdb_id) && (
          <div className="mt-2 flex gap-3 text-sm">
            {release.tmdb_id && (
              <a
                href={`https://www.themoviedb.org/${release.content_type === "tv" ? "tv" : "movie"}/${release.tmdb_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                TMDB ↗
              </a>
            )}
            {release.imdb_id && (
              <a
                href={`https://www.imdb.com/title/${release.imdb_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                IMDb ↗
              </a>
            )}
          </div>
        )}
      </div>

      {/* Fingerprint / metadata */}
      <div className="mb-6 rounded border border-neutral-200 bg-neutral-50 px-4 py-3 text-xs dark:border-neutral-800 dark:bg-neutral-900">
        <span className="font-medium">Fingerprint:</span>{" "}
        <code className="font-mono">{disc.fingerprint}</code>
        {disc.upc && (
          <>
            {" · "}
            <span className="font-medium">UPC:</span> {disc.upc}
          </>
        )}
        {disc.confidence && (
          <>
            {" · "}
            <span className="font-medium">Confidence:</span> {disc.confidence}
          </>
        )}
      </div>

      {/* Disc structure (titles) */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-3">Titles</h2>
        <DiscStructure titles={disc.titles} />
      </section>

      {/* Edit history */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Edit History</h2>
        <EditHistory edits={edits} />
      </section>

      {/* Dispute resolver (client component, renders only for trusted+ users) */}
      {disc.status === "disputed" && (
        <DisputeResolver fingerprint={fingerprint} conflictData={null} />
      )}
    </div>
  );
}
