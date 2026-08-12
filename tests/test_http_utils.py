from types import SimpleNamespace
from unittest import mock

import requests

from oz_tree_build.images import get_wiki_images
from oz_tree_build.utilities import http_utils


class TestRetryAfterSeconds:
    def test_uses_integer_retry_after_header(self):
        response = SimpleNamespace(headers={"Retry-After": "11"})
        assert http_utils.retry_after_seconds(response) == 11

    def test_uses_float_retry_after_header(self):
        response = SimpleNamespace(headers={"Retry-After": "11.5"})
        assert http_utils.retry_after_seconds(response) == 11.5

    def test_uses_large_retry_after_header(self):
        response = SimpleNamespace(headers={"Retry-After": "305"})
        assert http_utils.retry_after_seconds(response) == 305

    def test_recognises_when_no_header(self):
        response = SimpleNamespace(headers={})
        assert http_utils.retry_after_seconds(response) is None

    @mock.patch("oz_tree_build.utilities.http_utils.time.sleep")
    @mock.patch("oz_tree_build.utilities.http_utils.requests.get")
    def test_make_http_request_retries_using_retry_after(self, mock_get, mock_sleep):
        rate_limited = SimpleNamespace(status_code=429, headers={"Retry-After": "7"})
        ok = SimpleNamespace(status_code=200, headers={})
        mock_get.side_effect = [rate_limited, ok]

        response = http_utils.make_http_request_with_retries(
            "https://example.test/image.jpg",
            headers=get_wiki_images.USER_AGENT_HEADERS,
        )

        assert response is ok
        mock_sleep.assert_called_once_with(7)
        assert mock_get.call_count == 2
        assert mock_get.call_args.kwargs["timeout"] == http_utils.DEFAULT_TIMEOUT

    @mock.patch("oz_tree_build.utilities.http_utils.time.sleep")
    @mock.patch("oz_tree_build.utilities.http_utils.requests.get")
    def test_make_http_request_retries_on_timeout(self, mock_get, mock_sleep):
        ok = SimpleNamespace(status_code=200, headers={})
        mock_get.side_effect = [requests.exceptions.ReadTimeout("timed out"), ok]

        response = http_utils.make_http_request_with_retries(
            "https://example.test/image.jpg",
            headers=get_wiki_images.USER_AGENT_HEADERS,
        )

        assert response is ok
        mock_sleep.assert_called_once_with(5)
        assert mock_get.call_count == 2
