"use client";

import Button from "@/components/Button";

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

// Providers offered via the "Link a provider" add-flow. Mastodon and
// IndieAuth are excluded: `POST /v1/auth/link/{provider}` explicitly rejects
// them with 400 `link_requires_domain` (R-3, api/app/auth/routes.py) since
// they need a domain/url a bare add-flow request can't carry, and IndieAuth
// is hidden in production (D-05).
const LINKABLE_PROVIDERS = ["github", "google", "apple"];

export function providerLabel(provider: string): string {
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
  onLink?: (provider: string) => void;
  linking?: string | null;
}

export default function ProviderList({
  providers,
  onUnlink,
  unlinking = null,
  onLink,
  linking = null,
}: ProviderListProps) {
  const singleProvider = providers.length <= 1;
  const candidates = onLink
    ? LINKABLE_PROVIDERS.filter((provider) => !providers.includes(provider))
    : [];

  if (providers.length === 0 && candidates.length === 0) {
    return (
      <p className="text-sm text-neutral-500" data-testid="no-providers">
        No linked providers.
      </p>
    );
  }

  return (
    <div>
      {providers.length === 0 ? (
        <p className="text-sm text-neutral-500 mb-3" data-testid="no-providers">
          No linked providers.
        </p>
      ) : (
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
              <Button
                variant="ghost"
                onClick={() => onUnlink(provider)}
                disabled={singleProvider || unlinking === provider}
                data-testid={`unlink-${provider}`}
              >
                {unlinking === provider ? "Unlinking…" : "Unlink"}
              </Button>
            </li>
          ))}
        </ul>
      )}

      {onLink && candidates.length > 0 && (
        <ul
          className="divide-y divide-neutral-200 dark:divide-neutral-800 mt-4"
          data-testid="linkable-provider-list"
        >
          {candidates.map((provider) => (
            <li
              key={provider}
              className="flex items-center justify-between py-3"
              data-testid={`linkable-provider-${provider}`}
            >
              <span className="flex items-center gap-2 text-sm">
                <span>{providerIcon(provider)}</span>
                <span>{providerLabel(provider)}</span>
              </span>
              <Button
                variant="primary"
                onClick={() => onLink(provider)}
                disabled={linking === provider}
                data-testid={`link-${provider}`}
              >
                {linking === provider ? "Linking…" : "Link a provider"}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
