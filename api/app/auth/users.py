"""Shared OAuth-linking exceptions.

The legacy ``user_upsert``/``EmailConflictError`` identity-resolution path that
used to live here has been retired (LO-04): production callbacks route
exclusively through ``app.auth.merge.resolve_auth``, which is the sole
nOAuth-safe choke point (confirm-gated merge OFFER, never a silent attach).
``user_upsert`` hardcoded ``email_verified = provider == "github"`` and had no
offer gate, making it a divergent-trust landmine if a future caller wired it
back in.
"""


class ProviderAlreadyLinkedError(Exception):
    pass
