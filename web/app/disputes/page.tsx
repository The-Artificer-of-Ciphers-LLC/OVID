import Link from "next/link";
import { getDisputedDiscs } from "@/lib/api";

export const metadata = { title: "Disputed Discs — OVID" };

export default async function DisputesPage() {
  let data;
  try {
    data = await getDisputedDiscs();
  } catch {
    data = { results: [], total: 0, limit: 50, offset: 0, request_id: "" };
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-bold mb-2">Disputed Discs</h1>
      <p className="text-sm text-neutral-500 mb-6">
        {data.total} disc{data.total !== 1 ? "s" : ""} awaiting resolution
      </p>
      {data.results.length === 0 ? (
        <p className="text-neutral-400">No disputed discs.</p>
      ) : (
        <ul className="space-y-3">
          {data.results.map((disc) => (
            <li
              key={disc.fingerprint}
              className="rounded border border-neutral-200 dark:border-neutral-800 p-4"
            >
              <Link
                href={`/disc/${disc.fingerprint}`}
                className="font-medium hover:text-blue-600 transition-colors"
              >
                {disc.release?.title ?? disc.fingerprint}
              </Link>
              <div className="mt-1 text-xs text-neutral-500 flex gap-3">
                <span>{disc.format}</span>
                {disc.release?.year && <span>{disc.release.year}</span>}
                <span className="font-mono">
                  {disc.fingerprint.slice(0, 16)}…
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
