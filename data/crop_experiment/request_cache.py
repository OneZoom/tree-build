"""
A request-level cache for remote croppers. CachedTransport stands in for a cropper's
`transport` (see image_cropping.BaseCropper): each response is stored under
cache/requests/, keyed by a hash of the call's arguments (an OpenRouter request's URL
and JSON body, picture included; an Azure call's image URL or bytes), so reruns cost
nothing and a change to what a cropper sends misses the cache by itself.
"""

import hashlib
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "cache" / "requests"


def _digest_bytes(value):
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest()}
    raise TypeError(f"can't key a request on {type(value).__name__}")


def cache_path(args):
    request = json.dumps(args, sort_keys=True, separators=(",", ":"), default=_digest_bytes)
    key = hashlib.sha256(request.encode()).hexdigest()
    return CACHE_DIR / key[:2] / f"{key}.json"


class CachedTransport:
    """Answers from the cache, else from `live` (and caches the answer)."""

    def __init__(self, live):
        self.live = live

    def __call__(self, *args):
        path = cache_path(args)
        if path.exists():
            return json.loads(path.read_text())
        response = self.live(*args)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{id(self)}.tmp")
        tmp.write_text(json.dumps(response))
        tmp.replace(path)
        return response
