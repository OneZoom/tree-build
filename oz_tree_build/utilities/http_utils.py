"""Shared HTTP helpers for Wikimedia harvesting scripts."""

import datetime
import logging
import time
from email.utils import parsedate_to_datetime

import requests

logger = logging.getLogger(__name__)

DEFAULT_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 120
DEFAULT_TIMEOUT = (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT)


class HttpRequestError(Exception):
    """Raised when an HTTP request fails after retries."""


def retry_after_seconds(response) -> float | None:
    """
    Seconds to wait before retrying, honoring Retry-After when present.

    Wikimedia rate limits: https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        retry_after = retry_after.strip()
        try:
            return max(float(retry_after), 0)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=datetime.timezone.utc)
                wait = (retry_at - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
                return max(wait, 0)
            except (TypeError, ValueError, OverflowError):
                pass
    return None


def make_http_request_with_retries(
    url,
    *,
    params=None,
    data=None,
    stream=False,
    headers,
    method="GET",
    retry_status_codes=DEFAULT_RETRY_STATUS_CODES,
    timeout=DEFAULT_TIMEOUT,
):
    """
    Make an HTTP request to the given URL with the given headers,
    retrying if we get a rate limit, transient server error, or transport failure.
    """
    retries = 6
    delay = 5
    method = method.upper()
    for i in range(retries):
        try:
            if method == "GET":
                r = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    stream=stream,
                    timeout=timeout,
                )
            elif method == "POST":
                r = requests.post(
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                    stream=stream,
                    timeout=timeout,
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except requests.RequestException as exc:
            logger.warning("HTTP request failed on attempt %s for %s: %s", i + 1, url, exc)
            if i == retries - 1:
                raise HttpRequestError(f"Failed to get {url} after {retries} attempts: {exc}") from exc
            wait = min(max(delay, 5), 60)
            time.sleep(wait)
            delay *= 2
            continue

        if r.status_code == 200:
            return r

        if r.status_code in retry_status_codes:
            wait = retry_after_seconds(r) or delay
            logger.warning(
                "Rate limited (HTTP %s) on attempt %s for %s; retrying in %ss",
                r.status_code,
                i + 1,
                url,
                wait,
            )
            time.sleep(wait)
            delay *= 2
        else:
            raise HttpRequestError(f"Error requesting {url}: {r.status_code} {r.text}")

    raise HttpRequestError(f"Failed to get {url} after {retries} attempts")
