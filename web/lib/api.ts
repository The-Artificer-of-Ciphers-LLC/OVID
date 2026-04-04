// OVID API client -- typed fetch wrapper for both server and client components.

// ---------------------------------------------------------------------------
// Base URL resolution
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  // Server-side: use internal Docker network URL
  if (typeof window === "undefined") {
    return process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  }
  // Client-side: use public URL
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${getBaseUrl()}${path}`;
  const res = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: "unknown", message: res.statusText }));
    throw new ApiError(res.status, body.error ?? "api_error", body.message ?? body.detail ?? res.statusText);
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

export interface TitleResponse {
  title_index: number;
  is_main_feature: boolean;
  title_type: string | null;
  display_name: string | null;
  duration_secs: number | null;
  chapter_count: number | null;
  audio_tracks: TrackResponse[];
  subtitle_tracks: TrackResponse[];
}

export interface ReleaseResponse {
  title: string;
  year: number | null;
  content_type: string;
  tmdb_id: number | null;
  imdb_id: string | null;
}

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
}

// Request types
export interface TrackCreate {
  track_index: number;
  language_code: string | null;
  codec: string | null;
  channels: number | null;
  is_default: boolean;
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
  release: ReleaseCreate;
  titles: TitleCreate[];
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
): Promise<DiscSubmitResponse> {
  return apiFetch<DiscSubmitResponse>("/v1/disc", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getMe(): Promise<UserResponse> {
  return apiFetch<UserResponse>("/v1/auth/me");
}

export function getProviders(): Promise<ProvidersResponse> {
  return apiFetch<ProvidersResponse>("/v1/auth/providers");
}

export function unlinkProvider(
  provider: string,
): Promise<{ status: string; provider: string }> {
  return apiFetch<{ status: string; provider: string }>(
    `/v1/auth/unlink/${encodeURIComponent(provider)}`,
    { method: "DELETE" },
  );
}

// Dispute / UPC functions

export function getDisputedDiscs(limit = 50, offset = 0): Promise<DisputedDiscsResponse> {
  return apiFetch<DisputedDiscsResponse>(`/v1/disc/disputed?limit=${limit}&offset=${offset}`);
}

export function resolveDispute(
  fingerprint: string,
  action: "verify" | "reject",
): Promise<ResolveDisputeResponse> {
  return apiFetch<ResolveDisputeResponse>(`/v1/disc/${encodeURIComponent(fingerprint)}/resolve`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export function lookupByUpc(upc: string): Promise<UpcLookupResponse> {
  return apiFetch<UpcLookupResponse>(`/v1/disc/upc/${encodeURIComponent(upc)}`);
}
