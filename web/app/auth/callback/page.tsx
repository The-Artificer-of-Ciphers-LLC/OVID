"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { exchangeAuthCode } from "@/lib/auth";
import { Suspense } from "react";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    if (!code) {
      setError("No authorization code received.");
      return;
    }

    exchangeAuthCode(code)
      .then((success) => {
        if (success) {
          router.replace("/");
        } else {
          setError("Failed to complete login. Please try again.");
        }
      })
      .catch(() => {
        setError("An error occurred during login. Please try again.");
      });
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <p className="text-sm text-red-600">{error}</p>
          <a href="/" className="text-sm text-blue-600 hover:underline">
            Return home
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        <p className="text-sm text-neutral-500">Completing login...</p>
      </div>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[50vh] items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        </div>
      }
    >
      <CallbackHandler />
    </Suspense>
  );
}
