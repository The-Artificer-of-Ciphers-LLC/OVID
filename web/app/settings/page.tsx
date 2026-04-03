"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { getProviders, unlinkProvider, ApiError } from "@/lib/api";
import ProviderList from "@/components/ProviderList";

export default function SettingsPage() {
  const { user, token, loading } = useAuth();
  const router = useRouter();

  const [providers, setProviders] = useState<string[]>([]);
  const [providersLoading, setProvidersLoading] = useState(true);
  const [unlinking, setUnlinking] = useState<string | null>(null);
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
      setError(err instanceof ApiError ? err.message : "Failed to unlink provider.");
    } finally {
      setUnlinking(null);
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
          />
        )}
      </section>
    </div>
  );
}
