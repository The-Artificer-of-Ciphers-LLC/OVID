"""User upsert helper for OAuth flows."""

import logging

from sqlalchemy.orm import Session

from app.models import User, UserOAuthLink

logger = logging.getLogger(__name__)


def user_upsert(
    db: Session,
    *,
    provider: str,
    provider_id: str,
    email: str | None,
    display_name: str | None,
) -> User:
    """Find or create a user via their OAuth provider link.

    If a UserOAuthLink exists for (provider, provider_id), return the linked
    user.  Otherwise create a new User + UserOAuthLink and return the user.

    This is idempotent — calling twice with the same provider_id returns the
    same User row.
    """
    link = (
        db.query(UserOAuthLink)
        .filter(
            UserOAuthLink.provider == provider,
            UserOAuthLink.provider_id == provider_id,
        )
        .first()
    )

    if link is not None:
        logger.info("auth_callback provider=%s user_id=%s (existing)", provider, link.user_id)
        return link.user

    # Create new user + link
    user = User(
        username=f"{provider}_{provider_id}",
        email=email or f"{provider}_{provider_id}@noemail.placeholder",
        display_name=display_name,
        email_verified=provider == "github",  # GitHub emails are verified
    )
    db.add(user)
    db.flush()

    oauth_link = UserOAuthLink(
        user_id=user.id,
        provider=provider,
        provider_id=provider_id,
    )
    db.add(oauth_link)
    db.commit()
    db.refresh(user)

    logger.info("auth_callback provider=%s user_id=%s (new)", provider, user.id)
    return user
