"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { submitDisc, ApiError, type DiscSubmitRequest, type TitleCreate, type DiscSetSearchResult } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import SetSearchInput from "@/components/SetSearchInput";

// ---------------------------------------------------------------------------
// Types for the fingerprint JSON emitted by `ovid fingerprint --json`
// ---------------------------------------------------------------------------

interface FingerprintJson {
  fingerprint: string;
  format: string;
  structure?: {
    titles?: unknown[];
    playlists?: unknown[];
  };
}

function parseTitleCount(data: FingerprintJson): number {
  if (data.structure?.titles) return data.structure.titles.length;
  if (data.structure?.playlists) return data.structure.playlists.length;
  return 0;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SubmitForm() {
  const router = useRouter();
  const { user } = useAuth();

  // Parsed fingerprint data
  const [fpData, setFpData] = useState<FingerprintJson | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  // Form fields
  const [editionName, setEditionName] = useState("");
  const [discNumber, setDiscNumber] = useState(1);
  const [totalDiscs, setTotalDiscs] = useState(1);
  const [releaseTitle, setReleaseTitle] = useState("");
  const [releaseYear, setReleaseYear] = useState<number | "">("");
  const [contentType, setContentType] = useState("movie");

  // Set state
  const [isPartOfSet, setIsPartOfSet] = useState(false);
  const [selectedSetId, setSelectedSetId] = useState<string | null>(null);
  const [selectedSetInfo, setSelectedSetInfo] = useState<DiscSetSearchResult | null>(null);
  const [isCreatingNewSet, setIsCreatingNewSet] = useState(false);

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  // -----------------------------------------------------------------------
  // File handler
  // -----------------------------------------------------------------------

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    setParseError(null);
    setSubmitError(null);
    setSubmitSuccess(null);
    setFpData(null);

    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      try {
        const json = JSON.parse(reader.result as string);
        if (!json.fingerprint || !json.format) {
          setParseError(
            "Invalid fingerprint file: missing 'fingerprint' or 'format' field. Use 'ovid fingerprint --json' to generate a valid file.",
          );
          return;
        }
        setFpData(json as FingerprintJson);
      } catch {
        setParseError("Failed to parse JSON. Ensure the file is valid JSON.");
      }
    };
    reader.onerror = () => setParseError("Failed to read the file.");
    reader.readAsText(file);
  }

  // -----------------------------------------------------------------------
  // Submit handler
  // -----------------------------------------------------------------------

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!fpData || !user) return;

    const trimmedTitle = releaseTitle.trim();
    if (!trimmedTitle) {
      setSubmitError("Release title is required.");
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    const payload: DiscSubmitRequest = {
      fingerprint: fpData.fingerprint,
      format: fpData.format,
      edition_name: editionName.trim() || undefined,
      disc_number: discNumber,
      total_discs: totalDiscs,
      disc_set_id: selectedSetId ?? undefined,
      release: {
        title: trimmedTitle,
        year: releaseYear === "" ? null : releaseYear,
        content_type: contentType,
      },
      titles: [] as TitleCreate[],
    };

    try {
      const result = await submitDisc(payload);
      setSubmitSuccess(result.message ?? "Disc submitted successfully.");
      // Redirect to disc detail page after a short delay so the user sees the success message
      setTimeout(() => {
        router.push(`/disc/${encodeURIComponent(fpData.fingerprint)}`);
      }, 1200);
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(`${err.message} (${err.code})`);
      } else {
        setSubmitError("An unexpected error occurred.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  // -----------------------------------------------------------------------
  // Shared input class
  // -----------------------------------------------------------------------

  const EDITION_SUGGESTIONS = [
    "Extended Edition", "Director's Cut", "Theatrical",
    "Criterion Collection", "Special Edition", "Ultimate Edition",
  ];

  const inputClass =
    "w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-neutral-700 dark:bg-neutral-900";

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div>
      {/* File input */}
      <div className="mb-6">
        <label htmlFor="fp-file" className="block text-sm font-medium mb-1">
          Fingerprint JSON file
        </label>
        <input
          id="fp-file"
          type="file"
          accept=".json"
          onChange={handleFileChange}
          data-testid="fp-file-input"
          className="block w-full text-sm text-neutral-500 file:mr-3 file:rounded file:border-0 file:bg-blue-600 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-blue-700 file:cursor-pointer file:transition-colors"
        />
        <p className="mt-1 text-xs text-neutral-400">
          Generate with: <code>ovid fingerprint /dev/disc0 --json &gt; disc.json</code>
        </p>
      </div>

      {parseError && (
        <div
          data-testid="parse-error"
          className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
        >
          {parseError}
        </div>
      )}

      {/* Preview + form */}
      {fpData && (
        <form onSubmit={handleSubmit}>
          {/* Preview card */}
          <div
            data-testid="fp-preview"
            className="mb-6 rounded border border-neutral-200 bg-neutral-50 p-4 text-sm dark:border-neutral-800 dark:bg-neutral-900"
          >
            <h3 className="font-semibold mb-2">Fingerprint Preview</h3>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-neutral-500">Fingerprint</dt>
              <dd className="font-mono text-xs break-all">{fpData.fingerprint}</dd>
              <dt className="text-neutral-500">Format</dt>
              <dd>{fpData.format}</dd>
              <dt className="text-neutral-500">Titles</dt>
              <dd>{parseTitleCount(fpData)}</dd>
            </dl>
          </div>

          {/* Release metadata fields */}
          <fieldset className="mb-6 space-y-4">
            <legend className="text-sm font-semibold mb-2">Release Details</legend>

            <div>
              <label htmlFor="release-title" className="block text-sm font-medium mb-1">
                Release Title <span className="text-red-500">*</span>
              </label>
              <input
                id="release-title"
                type="text"
                required
                value={releaseTitle}
                onChange={(e) => setReleaseTitle(e.target.value)}
                placeholder="e.g. Blade Runner 2049"
                className={inputClass}
              />
            </div>

            <div className="flex gap-4">
              <div className="flex-1">
                <label htmlFor="release-year" className="block text-sm font-medium mb-1">
                  Year
                </label>
                <input
                  id="release-year"
                  type="number"
                  min={1900}
                  max={2099}
                  value={releaseYear}
                  onChange={(e) =>
                    setReleaseYear(e.target.value === "" ? "" : Number(e.target.value))
                  }
                  placeholder="e.g. 2017"
                  className={inputClass}
                />
              </div>
              <div className="flex-1">
                <label htmlFor="content-type" className="block text-sm font-medium mb-1">
                  Content Type
                </label>
                <select
                  id="content-type"
                  value={contentType}
                  onChange={(e) => setContentType(e.target.value)}
                  className={inputClass}
                >
                  <option value="movie">Movie</option>
                  <option value="tv_show">TV Show</option>
                </select>
              </div>
            </div>
          </fieldset>

          {/* Disc metadata fields */}
          <fieldset className="mb-6 space-y-4">
            <legend className="text-sm font-semibold mb-2">Disc Details</legend>

            <div>
              <label htmlFor="edition-name" className="block text-sm font-medium mb-1">
                Edition Name
              </label>
              <input
                id="edition-name"
                type="text"
                value={editionName}
                onChange={(e) => setEditionName(e.target.value)}
                placeholder="e.g. Director's Cut, Criterion Collection"
                className={inputClass}
              />
            </div>
          </fieldset>

          {/* Set toggle */}
          <div className="mb-6">
            <label className="relative inline-flex items-center cursor-pointer gap-2">
              <input
                type="checkbox"
                className="sr-only peer"
                checked={isPartOfSet}
                onChange={(e) => {
                  setIsPartOfSet(e.target.checked);
                  if (!e.target.checked) {
                    setSelectedSetId(null);
                    setSelectedSetInfo(null);
                    setIsCreatingNewSet(false);
                    setDiscNumber(1);
                    setTotalDiscs(1);
                  }
                }}
                data-testid="set-toggle"
              />
              <div className="w-9 h-5 bg-neutral-200 peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:bg-blue-600 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full dark:bg-neutral-700" />
              <span className="text-sm font-normal">Part of a multi-disc set?</span>
            </label>
          </div>

          {isPartOfSet && (
            <fieldset className="mb-6 space-y-4 transition-all duration-200" data-testid="set-fields">
              <legend className="text-sm font-semibold mb-2">Set Details</legend>

              {!isCreatingNewSet && !selectedSetInfo && (
                <SetSearchInput
                  onSelect={(setId, setInfo) => {
                    setSelectedSetId(setId);
                    setSelectedSetInfo(setInfo);
                  }}
                  onCreateNew={() => setIsCreatingNewSet(true)}
                />
              )}

              {selectedSetInfo && (
                <div className="rounded border border-neutral-200 bg-neutral-50 p-3 text-sm dark:border-neutral-800 dark:bg-neutral-900">
                  Selected: {selectedSetInfo.edition_name ?? "Unnamed set"} ({selectedSetInfo.discs.length}/{selectedSetInfo.total_discs} discs)
                  <button type="button" className="ml-2 text-blue-600 text-xs" onClick={() => { setSelectedSetId(null); setSelectedSetInfo(null); }}>Change</button>
                </div>
              )}

              {isCreatingNewSet && (
                <div>
                  <label htmlFor="set-edition-name" className="block text-sm font-medium mb-1">Edition Name</label>
                  <input
                    id="set-edition-name"
                    type="text"
                    list="edition-suggestions"
                    value={editionName}
                    onChange={(e) => setEditionName(e.target.value)}
                    placeholder="e.g. Extended Edition"
                    className={inputClass}
                    data-testid="set-edition-name"
                  />
                  <datalist id="edition-suggestions">
                    {EDITION_SUGGESTIONS.map(s => <option key={s} value={s} />)}
                  </datalist>
                </div>
              )}

              <div className="flex gap-4">
                <div className="flex-1">
                  <label htmlFor="disc-number" className="block text-sm font-medium mb-1">Disc Number</label>
                  <input id="disc-number" type="number" min={1} value={discNumber} onChange={(e) => setDiscNumber(Number(e.target.value))} className={inputClass} />
                </div>
                <div className="flex-1">
                  <label htmlFor="total-discs" className="block text-sm font-medium mb-1">Total Discs</label>
                  <input id="total-discs" type="number" min={1} value={totalDiscs} onChange={(e) => setTotalDiscs(Number(e.target.value))} className={inputClass} />
                </div>
              </div>
            </fieldset>
          )}

          {/* Error / success messages */}
          {submitError && (
            <div
              data-testid="submit-error"
              className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
            >
              {submitError}
            </div>
          )}
          {submitSuccess && (
            <div
              data-testid="submit-success"
              className="mb-4 rounded border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700 dark:border-green-800 dark:bg-green-950 dark:text-green-300"
            >
              {submitSuccess}
            </div>
          )}

          {/* Submit button */}
          <button
            type="submit"
            disabled={submitting}
            className="rounded bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "Submitting…" : "Submit Disc"}
          </button>
        </form>
      )}
    </div>
  );
}
