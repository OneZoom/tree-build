from types import SimpleNamespace
from unittest import mock

import pytest

from oz_tree_build.user_agent import USER_AGENT_HEADERS
from oz_tree_build.utilities.http_utils import DEFAULT_TIMEOUT, HttpRequestError
from oz_tree_build.utilities.wikimedia_auth import (
    TOKEN_URL,
    WikimediaAuth,
    auth_from_cli_credentials,
)


def token_response(access_token="test-token", expires_in=14400, status_code=200):
    return SimpleNamespace(
        status_code=status_code,
        headers={},
        text="",
        json=lambda: {"access_token": access_token, "expires_in": expires_in},
    )


class TestAuthFromCredentials:
    def test_returns_none_when_neither_is_set(self):
        assert auth_from_cli_credentials(None, None) is None
        assert auth_from_cli_credentials("", "") is None

    def test_requires_both_credentials(self):
        with pytest.raises(ValueError, match="Both --wikimedia-client-id"):
            auth_from_cli_credentials("id-only", None)
        with pytest.raises(ValueError, match="Both --wikimedia-client-id"):
            auth_from_cli_credentials(None, "secret-only")


class TestWikimediaAuth:
    def test_requires_both_credentials(self):
        with pytest.raises(ValueError, match="Both Wikimedia client id"):
            WikimediaAuth("id-only", None)
        with pytest.raises(ValueError, match="Both Wikimedia client id"):
            WikimediaAuth(None, "secret-only")

    @mock.patch("oz_tree_build.utilities.http_utils.requests.post")
    def test_fetches_token_and_builds_headers(self, mock_post):
        mock_post.return_value = token_response()
        auth = WikimediaAuth("the-id", "the-secret")

        headers = auth.headers()

        mock_post.assert_called_once_with(
            TOKEN_URL,
            params=None,
            data={
                "grant_type": "client_credentials",
                "client_id": "the-id",
                "client_secret": "the-secret",
            },
            headers=USER_AGENT_HEADERS,
            stream=False,
            timeout=DEFAULT_TIMEOUT,
        )
        assert headers == {"Authorization": "Bearer test-token"}

    @mock.patch("oz_tree_build.utilities.wikimedia_auth.time.time", return_value=1000)
    @mock.patch("oz_tree_build.utilities.http_utils.requests.post")
    def test_reuses_token_until_near_expiry(self, mock_post, mock_time):
        mock_post.return_value = token_response(expires_in=14400)
        auth = WikimediaAuth("the-id", "the-secret")

        assert auth.access_token() == "test-token"
        mock_time.return_value = 1000 + 14300
        assert auth.access_token() == "test-token"
        assert mock_post.call_count == 1

        mock_post.return_value = token_response(access_token="refreshed-token")
        mock_time.return_value = 1000 + 14350
        assert auth.access_token() == "refreshed-token"
        assert mock_post.call_count == 2

    @mock.patch("oz_tree_build.utilities.http_utils.requests.post")
    def test_raises_when_token_is_missing(self, mock_post):
        mock_post.return_value = SimpleNamespace(
            status_code=200,
            headers={},
            text="{}",
            json=lambda: {"error": "invalid_client"},
        )
        auth = WikimediaAuth("the-id", "the-secret")

        with pytest.raises(HttpRequestError, match="missing access_token"):
            auth.access_token()

    @mock.patch("oz_tree_build.utilities.http_utils.requests.post")
    def test_raises_when_expires_in_is_missing(self, mock_post):
        mock_post.return_value = SimpleNamespace(
            status_code=200,
            headers={},
            text="",
            json=lambda: {"access_token": "test-token"},
        )
        auth = WikimediaAuth("the-id", "the-secret")

        with pytest.raises(HttpRequestError, match="missing expires_in"):
            auth.access_token()
