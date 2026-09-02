"""OAuth 2.0 client-credentials auth for Wikimedia APIs."""

import logging
import time

from ..user_agent import USER_AGENT_HEADERS
from .http_utils import DEFAULT_TIMEOUT, HttpRequestError, make_http_request_with_retries

logger = logging.getLogger(__name__)

TOKEN_URL = "https://meta.wikimedia.org/w/rest.php/oauth2/access_token"
TOKEN_REFRESH_MARGIN_SECONDS = 60


class WikimediaAuth:
    """
    Fetch and refresh OAuth 2 access tokens via the client-credentials grant.

    See https://www.mediawiki.org/wiki/Wikimedia_APIs/Authentication

    To request access to the OneZoom wiki bot credentials, get in touch with tree-build maintainers.
    Jared Khan created the bot account.
    Alternatively, register a new app at:
    https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose/oauth2
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        if not client_id or not client_secret:
            raise ValueError("Both Wikimedia client id and client secret are required")
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    def access_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - TOKEN_REFRESH_MARGIN_SECONDS:
            return self._access_token
        self._fetch_access_token()
        assert self._access_token is not None
        return self._access_token

    def headers(self) -> dict[str, str]:
        """Authorization header with a Bearer token for Wikimedia API requests."""
        return {"Authorization": f"Bearer {self.access_token()}"}

    def _fetch_access_token(self) -> None:
        response = make_http_request_with_retries(
            TOKEN_URL,
            method="POST",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers=USER_AGENT_HEADERS,
            timeout=DEFAULT_TIMEOUT,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise HttpRequestError(f"Wikimedia token endpoint returned non-JSON: {response.text}") from exc
        token = payload.get("access_token")
        if not token:
            raise HttpRequestError(f"Wikimedia token response missing access_token: {payload}")
        if "expires_in" not in payload:
            raise HttpRequestError(f"Wikimedia token response missing expires_in: {payload}")
        try:
            expires_in = float(payload["expires_in"])
        except (TypeError, ValueError) as exc:
            raise HttpRequestError(f"Wikimedia token response has invalid expires_in: {payload}") from exc
        self._access_token = token
        self._expires_at = time.time() + max(expires_in, 0)
        logger.info("Fetched Wikimedia OAuth access token (expires in %.0fs)", expires_in)


def auth_from_cli_credentials(client_id: str | None, client_secret: str | None) -> WikimediaAuth | None:
    """
    Build a WikimediaAuth from CLI credentials.

    Returns None when neither is set. Raises ValueError if only one is set.
    """
    if not client_id and not client_secret:
        return None
    if not client_id or not client_secret:
        raise ValueError("Both --wikimedia-client-id and --wikimedia-client-secret must be provided")
    return WikimediaAuth(client_id, client_secret)
