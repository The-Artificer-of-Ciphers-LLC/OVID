// OVID API client — typed fetch wrapper for both server and client components.

// ---------------------------------------------------------------------------
// Base URL resolution
// ---------------------------------------------------------------------------

export function getBaseUrl(): string {
  // Server-side: use internal Docker network URL
  if (typeof window === "undefined") {
    return process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  }
  // Client-side: use public URL
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

// Extracts {error, message} from either of the two error envelope
// conventions this API uses: the flat disc/set `_error_response` shape
// ({error, message}) or FastAPI's default `HTTPException(detail={...})`
// shape, which nests everything under a `detail` key ({detail: {error,
// reason}}) — and `detail` can also be a plain string for framework-level
// errors (e.g. auth dependency failures). Falling back to `body.error`
// alone (the disc/set-only shape) silently produced `code: "api_error"` and
// an unreadable "[object Object]" message for every auth-route error.
function extractErrorDetail(
  body: unknown,
  statusText: string,
): { error: string; message: string } {
  const record = (body ?? {}) as Record<string, unknown>;
  const detail = record.detail;
  const stringDetail = typeof detail === "string" ? detail : undefined;
  const nested =
    detail && typeof detail === "object" ? (detail as Record<string, unknown>) : record;

  const error = typeof nested.error === "string" ? nested.error : "api_error";
  const message =
    (typeof nested.message === "string" && nested.message) ||
    (typeof nested.reason === "string" && nested.reason) ||
    stringDetail ||
    statusText;

  return { error, message };
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${getBaseUrl()}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: "unknown", message: res.statusText }));
    const { error, message } = extractErrorDetail(body, res.statusText);
    throw new ApiError(res.status, error, message);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Error class
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// Response types (mirrors api/app/schemas.py)
// ---------------------------------------------------------------------------

export interface TrackResponse {
  index: number;
  language: string | null;
  codec: string | null;
  channels: number | null;
  is_default: boolean;
}

export interface ChapterResponse {
  chapter_index: number;
  name: string | null;
  start_time_secs: number | null;
}

export interface TitleResponse {
  title_index: number;
  is_main_feature: boolean;
  title_type: string | null;
  display_name: string | null;
  duration_secs: number | null;
  chapter_count: number | null;
  audio_tracks: TrackResponse[];
  subtitle_tracks: TrackResponse[];
  chapters: ChapterResponse[];
}

export interface ReleaseResponse {
  title: string;
  year: number | null;
  content_type: string;
  tmdb_id: number | null;
  imdb_id: string | null;
}

// One known Disc Identity string for a pressing (IDENT-01). Optional on
// DiscLookupResponse so existing, unmodified callers keep working (D-07).
export interface FingerprintAlias {
  fingerprint: string;
  method: string;
  is_primary: boolean;
}

// --- Disc Set types (Phase 2) ---

export interface SiblingDiscSummary {
  fingerprint: string;
  disc_number: number;
  format: string;
  main_title: string | null;
  duration_secs: number | null;
  track_count: number | null;
}

export interface DiscSetNested {
  id: string;
  edition_name: string | null;
  total_discs: number;
  siblings: SiblingDiscSummary[];
}

export interface DiscSetSearchResult {
  request_id: string;
  id: string;
  release_id: string;
  edition_name: string | null;
  total_discs: number;
  discs: SiblingDiscSummary[];
}

export interface DiscSetSearchResponse {
  request_id: string;
  results: DiscSetSearchResult[];
  page: number;
  total_pages: number;
  total_results: number;
}

// ---------------------------------------------------------------------------

export interface DiscLookupResponse {
  request_id: string;
  fingerprint: string;
  format: string;
  status: string;
  confidence: string;
  region_code: string | null;
  upc: string | null;
  edition_name: string | null;
  disc_number: number;
  total_discs: number;
  submitted_by: string | null;
  verified_by: string | null;
  release: ReleaseResponse | null;
  titles: TitleResponse[];
  fingerprint_aliases?: FingerprintAlias[];
  disc_set: DiscSetNested | null;
}

// Request types
export interface TrackCreate {
  track_index: number;
  language_code: string | null;
  codec: string | null;
  channels: number | null;
  is_default: boolean;
}

export interface ChapterCreate {
  chapter_index: number;
  name: string | null;
  start_time_secs: number | null;
}

export interface TitleCreate {
  title_index: number;
  title_type: string | null;
  duration_secs: number | null;
  chapter_count: number | null;
  is_main_feature: boolean;
  display_name: string | null;
  audio_tracks: TrackCreate[];
  subtitle_tracks: TrackCreate[];
  chapters?: ChapterCreate[];
}

export interface ReleaseCreate {
  title: string;
  year: number | null;
  content_type: string;
  tmdb_id?: number | null;
  imdb_id?: string | null;
  original_language?: string | null;
}

export interface DiscSubmitRequest {
  fingerprint: string;
  format: string;
  region_code?: string | null;
  upc?: string | null;
  disc_label?: string | null;
  edition_name?: string | null;
  disc_number: number;
  total_discs: number;
  disc_set_id?: string | null;
  release: ReleaseCreate;
  titles: TitleCreate[];
  fingerprint_aliases?: string[];
}

export interface DiscSubmitResponse {
  request_id: string;
  fingerprint: string;
  status: string;
  message: string;
}

// Edit history
export interface DiscEditResponse {
  edit_type: string | null;
  field_changed: string | null;
  old_value: string | null;
  new_value: string | null;
  edit_note: string | null;
  created_at: string;
  user_id: string | null;
}

export interface DiscEditsListResponse {
  request_id: string;
  fingerprint: string;
  edits: DiscEditResponse[];
}

// Search
export interface SearchResultRelease {
  id: string;
  title: string;
  year: number | null;
  content_type: string;
  tmdb_id: number | null;
  disc_count: number;
}

export interface SearchResponse {
  request_id: string;
  results: SearchResultRelease[];
  page: number;
  total_pages: number;
  total_results: number;
}

// Auth
export interface UserResponse {
  id: string;
  username: string;
  email: string;
  display_name: string | null;
  role: string;
  email_verified: boolean;
}

export interface ProvidersResponse {
  providers: string[];
}

// Dispute / UPC response types
export interface DisputedDiscsResponse {
  request_id: string;
  total: number;
  limit: number;
  offset: number;
  results: DiscLookupResponse[];
}

export interface UpcLookupResponse {
  request_id: string;
  results: DiscLookupResponse[];
}

export interface ResolveDisputeResponse {
  request_id: string;
  status: string;
  message: string;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export function searchReleases(
  q: string,
  type?: string,
  year?: number,
  page?: number,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q });
  if (type) params.set("type", type);
  if (year != null) params.set("year", String(year));
  if (page != null) params.set("page", String(page));
  return apiFetch<SearchResponse>(`/v1/search?${params.toString()}`);
}

export function getDisc(fingerprint: string): Promise<DiscLookupResponse> {
  return apiFetch<DiscLookupResponse>(`/v1/disc/${encodeURIComponent(fingerprint)}`);
}

export function getDiscEdits(fingerprint: string): Promise<DiscEditsListResponse> {
  return apiFetch<DiscEditsListResponse>(`/v1/disc/${encodeURIComponent(fingerprint)}/edits`);
}

export function submitDisc(
  data: DiscSubmitRequest,
  token: string,
): Promise<DiscSubmitResponse> {
  return apiFetch<DiscSubmitResponse>("/v1/disc", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });
}

export function getMe(token: string): Promise<UserResponse> {
  return apiFetch<UserResponse>("/v1/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getProviders(token: string): Promise<ProvidersResponse> {
  return apiFetch<ProvidersResponse>("/v1/auth/providers", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function unlinkProvider(
  provider: string,
  token: string,
): Promise<{ status: string; provider: string }> {
  return apiFetch<{ status: string; provider: string }>(
    `/v1/auth/unlink/${encodeURIComponent(provider)}`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    },
  );
}

// ---------------------------------------------------------------------------
// Add-provider flow (WEBUI-04, D-05 "middle depth", 07-07 decision: option-b)
// ---------------------------------------------------------------------------

/**
 * Starts the authenticated "link a provider" flow. `POST /v1/auth/link/{provider}`
 * requires Bearer auth and sets `link_to_user_id` in the session cookie, then
 * 302s to `/v1/auth/{provider}/login` — a plain top-level navigation can't
 * carry the Bearer header, and a followed `fetch` can't carry the browser
 * through the cross-origin provider redirect. So this primes the session
 * cookie via a credentialed, non-following fetch first, then returns the
 * deterministic `/login` URL for the caller to `window.location.assign` as a
 * top-level navigation (which now carries the session-cookie-authenticated
 * OAuth round-trip).
 */
export async function linkProvider(provider: string, token: string): Promise<string> {
  const base = getBaseUrl();
  const res = await fetch(`${base}/v1/auth/link/${encodeURIComponent(provider)}`, {
    method: "POST",
    credentials: "include",
    redirect: "manual",
    headers: { Authorization: `Bearer ${token}` },
  });

  // Under redirect: "manual", the endpoint's normal 302 becomes an opaque
  // "opaqueredirect" response (status 0, headers unreadable) — but the
  // browser still processes the Set-Cookie on that response before
  // opacifying it, so the session-priming side effect this call exists for
  // still happens. A genuine non-redirect failure (400 invalid_provider /
  // link_requires_domain, 401 unauthenticated) IS a normal readable response
  // and must surface as an ApiError.
  if (res.type !== "opaqueredirect" && !res.ok) {
    const body = await res.json().catch(() => ({ error: "unknown", message: res.statusText }));
    const { error, message } = extractErrorDetail(body, res.statusText);
    throw new ApiError(res.status, error, message);
  }

  // The redirect target is deterministic server-side
  // (`RedirectResponse(url=f"/v1/auth/{provider}/login")`) — construct it
  // directly rather than trying to read the opaque response's Location.
  const callbackUrl = `${window.location.origin}/auth/callback`;
  return `${base}/v1/auth/${encodeURIComponent(provider)}/login?web_redirect_uri=${encodeURIComponent(callbackUrl)}`;
}

// Dispute / UPC functions

export function getDisputedDiscs(limit = 50, offset = 0): Promise<DisputedDiscsResponse> {
  return apiFetch<DisputedDiscsResponse>(`/v1/disc/disputed?limit=${limit}&offset=${offset}`);
}

export function resolveDispute(
  fingerprint: string,
  action: "verify" | "reject",
  token: string,
): Promise<ResolveDisputeResponse> {
  return apiFetch<ResolveDisputeResponse>(`/v1/disc/${encodeURIComponent(fingerprint)}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ action }),
  });
}

export function lookupByUpc(upc: string): Promise<UpcLookupResponse> {
  return apiFetch<UpcLookupResponse>(`/v1/disc/upc/${encodeURIComponent(upc)}`);
}

// ---------------------------------------------------------------------------
// Disc Set functions (Phase 2)
// ---------------------------------------------------------------------------

export function searchSets(q: string, page?: number): Promise<DiscSetSearchResponse> {
  const params = new URLSearchParams({ q });
  if (page != null) params.set("page", String(page));
  return apiFetch<DiscSetSearchResponse>(`/v1/set?${params.toString()}`);
}

export function createSet(data: { release_id: string; edition_name?: string | null; total_discs: number }): Promise<{ request_id: string; id: string; release_id: string; edition_name: string | null; total_discs: number; created_at: string }> {
  return apiFetch(`/v1/set`, { method: "POST", body: JSON.stringify(data) });
}
