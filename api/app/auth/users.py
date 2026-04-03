"""User upsert helper for OAuth flows."""

import logging
import uuid as _uuid

from sqlalchemy.orm import Session

from app.models import User, UserOAuthLink

logger = logging.getLogger(__name__)


class EmailConflictError(Exception):
    def __init__(self, existing_user_id: str, email: str):
        self.existing_user_id = existing_user_id
        self.email = email
        super().__init__(f"Email {email} is already registered")

class ProviderAlreadyLinkedError(Exception):
    pass

def user_upsert(
    db: Session,
    *,
    provider: str,
    provider_id: str,
    email: str | None,
    display_name: str | None,
    link_to_user_id: str | None = None,
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
        if link_to_user_id and str(link.user_id) != link_to_user_id:
            raise ProviderAlreadyLinkedError("Provider account is already linked to another user")
        logger.info("auth_callback provider=%s user_id=%s (existing)", provider, link.user_id)
        return link.user

    if link_to_user_id:
        try:
            _link_uuid = _uuid.UUID(link_to_user_id) if isinstance(link_to_user_id, str) else link_to_user_id
        except (ValueError, AttributeError):
            raise ValueError("Invalid user ID for explicit linking")
        user = db.query(User).filter(User.id == _link_uuid).first()
        if not user:
            raise ValueError("User not found for explicit linking")
        oauth_link = UserOAuthLink(
            user_id=user.id,
            provider=provider,
            provider_id=provider_id,
        )
        db.add(oauth_link)
        db.commit()
        db.refresh(user)
        logger.info("auth_callback provider=%s linked to user_id=%s", provider, user.id)
        return user

    # Implicit check for email conflict
    if email and not email.endswith("@noemail.placeholder"):
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise EmailConflictError(existing_user_id=str(existing_user.id), email=email)

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
