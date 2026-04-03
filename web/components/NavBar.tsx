"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CALLBACK_URL =
  typeof window !== "undefined"
    ? `${window.location.origin}/auth/callback`
    : "http://localhost:3000/auth/callback";

export default function NavBar() {
  const { user, loading, logout } = useAuth();

  const loginUrl = `${API_URL}/v1/auth/github/login?web_redirect_uri=${encodeURIComponent(CALLBACK_URL)}`;

  return (
    <nav className="border-b border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        {/* Logo / brand */}
        <Link href="/" className="flex items-center gap-2 text-lg font-bold tracking-tight">
          <span className="text-blue-600">◉</span> OVID
        </Link>

        {/* Navigation links */}
        <div className="flex items-center gap-4 text-sm">
          <Link href="/" className="hover:text-blue-600 transition-colors">
            Search
          </Link>
          <Link href="/submit" className="hover:text-blue-600 transition-colors">
            Submit
          </Link>
          <Link href="/disputes" className="hover:text-blue-600 transition-colors">
            Disputes
          </Link>

          {loading ? (
            <span className="text-neutral-400 text-xs">…</span>
          ) : user ? (
            <div className="flex items-center gap-3">
              <Link href="/settings" className="hover:text-blue-600 transition-colors">
                {user.display_name ?? user.username}
              </Link>
              <button
                onClick={logout}
                className="rounded bg-neutral-100 px-2 py-1 text-xs hover:bg-neutral-200 dark:bg-neutral-800 dark:hover:bg-neutral-700 transition-colors"
              >
                Logout
              </button>
            </div>
          ) : (
            <a
              href={loginUrl}
              className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700 transition-colors"
            >
              Login
            </a>
          )}
        </div>
      </div>
    </nav>
  );
}
