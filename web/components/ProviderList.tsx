"use client";

// ---------------------------------------------------------------------------
// Provider display names and icons
// ---------------------------------------------------------------------------

const PROVIDER_META: Record<string, { label: string; icon: string }> = {
  github: { label: "GitHub", icon: "🐙" },
  google: { label: "Google", icon: "🔵" },
  apple: { label: "Apple", icon: "🍎" },
  mastodon: { label: "Mastodon", icon: "🐘" },
  indieauth: { label: "IndieAuth", icon: "🌐" },
};

function providerLabel(provider: string): string {
  return PROVIDER_META[provider]?.label ?? provider;
}

function providerIcon(provider: string): string {
  return PROVIDER_META[provider]?.icon ?? "🔗";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ProviderListProps {
  providers: string[];
  onUnlink: (provider: string) => void;
  unlinking?: string | null;
}

export default function ProviderList({
  providers,
  onUnlink,
  unlinking = null,
}: ProviderListProps) {
  const singleProvider = providers.length <= 1;

  if (providers.length === 0) {
    return (
      <p className="text-sm text-neutral-400" data-testid="no-providers">
        No linked providers.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-neutral-200 dark:divide-neutral-800" data-testid="provider-list">
      {providers.map((provider) => (
        <li
          key={provider}
          className="flex items-center justify-between py-3"
          data-testid={`provider-${provider}`}
        >
          <span className="flex items-center gap-2 text-sm">
            <span>{providerIcon(provider)}</span>
            <span>{providerLabel(provider)}</span>
          </span>
          <button
            onClick={() => onUnlink(provider)}
            disabled={singleProvider || unlinking === provider}
            data-testid={`unlink-${provider}`}
            className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-40 disabled:cursor-not-allowed dark:border-neutral-700 dark:hover:bg-neutral-800 transition-colors"
          >
            {unlinking === provider ? "Unlinking…" : "Unlink"}
          </button>
        </li>
      ))}
    </ul>
  );
}
