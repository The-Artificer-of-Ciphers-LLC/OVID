"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { resolveDispute } from "@/lib/api";

interface Props {
  fingerprint: string;
  conflictData?: string | null;
}

const TRUSTED_ROLES = new Set(["trusted", "editor", "admin"]);

export default function DisputeResolver({ fingerprint, conflictData }: Props) {
  const { user, token } = useAuth();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user || !TRUSTED_ROLES.has(user.role ?? "")) return null;

  async function handleResolve(action: "verify" | "reject") {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      await resolveDispute(fingerprint, action, token);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resolution failed");
    } finally {
      setLoading(false);
    }
  }

  let parsed: Record<string, unknown> | null = null;
  if (conflictData) {
    try {
      parsed = JSON.parse(conflictData);
    } catch {
      /* ignore malformed JSON */
    }
  }

  return (
    <div className="mt-6 rounded border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950 p-4">
      <h2 className="text-sm font-semibold text-amber-800 dark:text-amber-200 mb-3">
        Resolve Dispute
      </h2>
      {parsed && (
        <div className="mb-3 text-xs text-neutral-600 dark:text-neutral-400">
          <p className="font-medium mb-1">Conflicting submission:</p>
          <pre className="bg-white dark:bg-neutral-900 rounded p-2 overflow-x-auto">
            {JSON.stringify(parsed, null, 2)}
          </pre>
        </div>
      )}
      {error && <p className="text-xs text-red-600 mb-2">{error}</p>}
      <div className="flex gap-2">
        <button
          disabled={loading}
          onClick={() => handleResolve("verify")}
          className="rounded bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
        >
          Mark Verified
        </button>
        <button
          disabled={loading}
          onClick={() => handleResolve("reject")}
          className="rounded bg-neutral-200 px-3 py-1.5 text-xs font-medium text-neutral-800 hover:bg-neutral-300 disabled:opacity-50 transition-colors dark:bg-neutral-700 dark:text-neutral-200"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
