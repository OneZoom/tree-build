from types import SimpleNamespace

from oz_tree_build.user_agent import USER_AGENT_HEADERS
from oz_tree_build.utilities.wikimedia_headers import wikimedia_headers


class TestWikimediaHeaders:
    def test_unauthenticated_headers_are_user_agent_only(self):
        assert wikimedia_headers(auth=None) is USER_AGENT_HEADERS
        assert "Authorization" not in wikimedia_headers(auth=None)

    def test_authenticated_headers_include_bearer_token(self):
        auth = SimpleNamespace(headers=lambda: {"Authorization": "Bearer wiki-token"})
        headers = wikimedia_headers(auth)
        assert headers["User-Agent"] == USER_AGENT_HEADERS["User-Agent"]
        assert headers["Authorization"] == "Bearer wiki-token"
