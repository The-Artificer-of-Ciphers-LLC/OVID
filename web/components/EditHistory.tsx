import type { DiscEditResponse } from "@/lib/api";

const EDIT_TYPE_COLORS: Record<string, string> = {
  create: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  update: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  verify: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  dispute: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function EditHistory({ edits }: { edits: DiscEditResponse[] }) {
  if (edits.length === 0) {
    return <p className="text-sm text-neutral-500">No edit history.</p>;
  }

  return (
    <ul className="space-y-3">
      {edits.map((edit, i) => {
        const badgeColor =
          EDIT_TYPE_COLORS[(edit.edit_type ?? "").toLowerCase()] ??
          "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300";

        return (
          <li
            key={i}
            className="rounded border border-neutral-200 bg-white p-3 text-sm dark:border-neutral-800 dark:bg-neutral-950"
            data-testid="edit-entry"
          >
            <div className="flex items-center gap-2 mb-1">
              {edit.edit_type && (
                <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${badgeColor}`}>
                  {edit.edit_type}
                </span>
              )}
              {edit.field_changed && (
                <span className="text-xs text-neutral-500">
                  {edit.field_changed}
                </span>
              )}
              <span className="ml-auto text-xs text-neutral-400">
                {formatDate(edit.created_at)}
              </span>
            </div>

            {(edit.old_value != null || edit.new_value != null) && (
              <p className="text-xs text-neutral-600 dark:text-neutral-400">
                {edit.old_value != null && (
                  <span className="line-through text-red-600 dark:text-red-400 mr-2">
                    {edit.old_value}
                  </span>
                )}
                {edit.new_value != null && (
                  <span className="text-green-600 dark:text-green-400">
                    → {edit.new_value}
                  </span>
                )}
              </p>
            )}

            {edit.edit_note && (
              <p className="mt-1 text-xs text-neutral-500 italic">
                {edit.edit_note}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
