"""HTTP headers for Wikimedia API requests."""

from ..user_agent import USER_AGENT_HEADERS
from .wikimedia_auth import WikimediaAuth


def wikimedia_headers(auth: WikimediaAuth | None) -> dict[str, str]:
    """User-Agent headers, plus a Bearer token when `auth` is provided."""
    if auth is None:
        return USER_AGENT_HEADERS
    return {**USER_AGENT_HEADERS, **auth.headers()}
