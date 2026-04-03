import type { TitleResponse } from "@/lib/api";

function formatDuration(secs: number | null): string {
  if (secs == null) return "—";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function summarizeTracks(
  tracks: { language: string | null; codec: string | null; channels: number | null }[],
): string {
  if (tracks.length === 0) return "—";
  return tracks
    .map((t) => {
      const lang = t.language?.toUpperCase() ?? "??";
      const codec = t.codec ?? "";
      const ch = t.channels != null ? `${t.channels}ch` : "";
      return [lang, codec, ch].filter(Boolean).join(" ");
    })
    .join(", ");
}

export default function DiscStructure({ titles }: { titles: TitleResponse[] }) {
  if (titles.length === 0) {
    return <p className="text-sm text-neutral-500">No title structure available.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-neutral-200 text-left text-xs text-neutral-500 dark:border-neutral-800">
            <th className="py-2 pr-3">#</th>
            <th className="py-2 pr-3">Title</th>
            <th className="py-2 pr-3">Duration</th>
            <th className="py-2 pr-3">Chapters</th>
            <th className="py-2 pr-3">Audio</th>
            <th className="py-2">Subtitles</th>
          </tr>
        </thead>
        <tbody>
          {titles.map((title) => (
            <tr
              key={title.title_index}
              className="border-b border-neutral-100 dark:border-neutral-800/50"
              data-testid="title-row"
            >
              <td className="py-2 pr-3 tabular-nums">{title.title_index}</td>
              <td className="py-2 pr-3 font-medium">
                {title.display_name ?? `Title ${title.title_index}`}
                {title.is_main_feature && (
                  <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                    Main
                  </span>
                )}
              </td>
              <td className="py-2 pr-3 tabular-nums">{formatDuration(title.duration_secs)}</td>
              <td className="py-2 pr-3 tabular-nums">{title.chapter_count ?? "—"}</td>
              <td className="py-2 pr-3 text-xs">{summarizeTracks(title.audio_tracks)}</td>
              <td className="py-2 text-xs">{summarizeTracks(title.subtitle_tracks)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
