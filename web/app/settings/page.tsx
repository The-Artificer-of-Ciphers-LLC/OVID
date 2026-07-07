"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { getProviders, unlinkProvider, linkProvider, getBaseUrl, ApiError } from "@/lib/api";
import ProviderList, { providerLabel } from "@/components/ProviderList";

function SettingsPageInner() {
  const { user, token, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [providers, setProviders] = useState<string[]>([]);
  const [providersLoading, setProvidersLoading] = useState(true);
  const [unlinking, setUnlinking] = useState<string | null>(null);
  const [linking, setLinking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Redirect unauthenticated users
  useEffect(() => {
    if (!loading && !user) {
      router.push("/?message=login_required");
    }
  }, [loading, user, router]);

  // Fetch linked providers
  const fetchProviders = useCallback(async () => {
    if (!token) return;
    setProvidersLoading(true);
    try {
      const res = await getProviders(token);
      setProviders(res.providers);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load providers.");
    } finally {
      setProvidersLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      fetchProviders();
    }
  }, [token, fetchProviders]);

  // Unlink a provider
  async function handleUnlink(provider: string) {
    if (!token) return;
    setUnlinking(provider);
    setError(null);
    try {
      await unlinkProvider(provider, token);
      await fetchProviders();
    } catch (err) {
      if (err instanceof ApiError && err.code === "cannot_unlink_last") {
        // UI-SPEC fixed copy — surfaced regardless of the backend's own
        // message wording, so it stays in our control.
        setError(
          "You must keep at least one login method. Link another provider before removing this one.",
        );
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to unlink provider.");
      }
    } finally {
      setUnlinking(null);
    }
  }

  // Link a provider (WEBUI-04 add path — 07-07 decision: option-b, frontend-only)
  async function handleLink(provider: string) {
    if (!token) return;
    setLinking(provider);
    setError(null);
    try {
      const loginUrl = await linkProvider(provider, token);
      window.location.assign(loginUrl);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start linking provider.");
      setLinking(null);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-12 text-center text-neutral-400 text-sm">
        Loading…
      </div>
    );
  }

  if (!user) {
    return null;
  }

  // Hide placeholder emails
  const showEmail =
    user.email && !user.email.endsWith("@noemail.placeholder");

  // D-05 enumeration-safe merge banner: reads the D-04 redirect
  // (?error=email_conflict&pending_link_id=) forwarded here by
  // /auth/callback. Names ONLY the current account's own linked providers
  // (ME-02) — never the matched/different account, its email, or its id.
  const mergeError = searchParams.get("error");
  const pendingLinkId = searchParams.get("pending_link_id");
  const showMergeBanner =
    mergeError === "email_conflict" && !providersLoading && providers.length > 0;
  const reAuthProvider = providers[0];
  const reAuthCallbackUrl =
    typeof window !== "undefined" ? `${window.location.origin}/auth/callback` : "";
  const reAuthUrl = showMergeBanner
    ? `${getBaseUrl()}/v1/auth/${encodeURIComponent(reAuthProvider)}/login?pending_link_id=${encodeURIComponent(pendingLinkId ?? "")}&web_redirect_uri=${encodeURIComponent(reAuthCallbackUrl)}`
    : "";

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-bold tracking-tight mb-6">Account Settings</h1>

      {/* Profile section */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-3">Profile</h2>
        <div className="rounded border border-neutral-200 bg-neutral-50 p-4 text-sm dark:border-neutral-800 dark:bg-neutral-900">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
            <dt className="text-neutral-500">Display Name</dt>
            <dd data-testid="profile-display-name">
              {user.display_name ?? "—"}
            </dd>
            <dt className="text-neutral-500">Username</dt>
            <dd data-testid="profile-username">{user.username}</dd>
            {showEmail && (
              <>
                <dt className="text-neutral-500">Email</dt>
                <dd data-testid="profile-email">{user.email}</dd>
              </>
            )}
            <dt className="text-neutral-500">Role</dt>
            <dd>{user.role}</dd>
          </dl>
        </div>
      </section>

      {/* Linked providers section */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Linked Providers</h2>

        {showMergeBanner && (
          <div
            role="alert"
            aria-live="polite"
            data-testid="merge-banner"
            className="mb-4 rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
          >
            This email is already linked to another OVID account via{" "}
            {providers.map(providerLabel).join(", ")}. To connect this login,
            re-authenticate with that provider.{" "}
            <a
              href={reAuthUrl}
              data-testid="merge-banner-reauth-link"
              className="font-medium underline"
            >
              Re-authenticate
            </a>
          </div>
        )}

        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
            {error}
          </div>
        )}
        {providersLoading ? (
          <p className="text-sm text-neutral-400">Loading providers…</p>
        ) : (
          <ProviderList
            providers={providers}
            onUnlink={handleUnlink}
            unlinking={unlinking}
            onLink={handleLink}
            linking={linking}
          />
        )}
      </section>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-2xl px-4 py-12 text-center text-neutral-400 text-sm">
          Loading…
        </div>
      }
    >
      <SettingsPageInner />
    </Suspense>
  );
}
