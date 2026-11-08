"""
Shared helpers for the croppers that ask a model via OpenRouter (https://openrouter.ai):
chat models through the chat completions API, decision models (e.g. TypeSafe's Jev)
through the Decisions API. The API key comes from the config's [openrouter] key.
"""

import base64
import io
import json
from functools import partial, reduce
from operator import add

from PIL import Image

from ...utilities.http_utils import HttpRequestError, make_http_request_with_retries
from .base import BaseCropper, CropResult, Usage
from .centre import centre_square
from .geometry import CropBox

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"


class OpenRouterError(Exception):
    pass


def post_json(url, body, api_key):
    """POST JSON, retrying on network errors, 429 and 5xx. Raises OpenRouterError with a short reason."""
    if not api_key:
        raise OpenRouterError("no OpenRouter API key: set [openrouter] key in the config file")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        return make_http_request_with_retries(url, method="POST", data=json.dumps(body), headers=headers).json()
    except HttpRequestError as e:
        raise OpenRouterError(str(e)[:400]) from e


def scaled(image, long_side, min_short_side=0):
    """The image scaled so its long side is `long_side`, or larger if needed for a short side of `min_short_side`."""
    scale = max(long_side / max(image.size), min_short_side / min(image.size))
    return image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)


def jpeg_bytes(picture):
    buf = io.BytesIO()
    picture.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def data_url(jpeg):
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()


def parse_box(answer):
    """{left, right, top, bottom} fractions from a Decisions API box answer, or None."""
    box = answer.get("box") if isinstance(answer.get("box"), dict) else answer
    try:
        return {k: float(box[k]) for k in ("left", "right", "top", "bottom")}
    except (KeyError, TypeError, ValueError):
        return None


def decide_box(post, model, jpeg, text, instructions, question_key):
    """One Decisions API request with a single box question; the box, or None."""
    body = {
        "model": model,
        "state": [{"type": "image_url", "image_url": {"url": data_url(jpeg)}}, text],
        "questions": {question_key: {"type": "box", "instructions": instructions}},
    }
    raw = post(DECISIONS_URL, body)
    return parse_box((raw.get("answers") or {}).get(question_key) or {})


def response_usage(raw):
    """The Usage a chat completions or Decisions API response reports."""
    u = raw.get("usage") or {}
    # Chat responses report reasoning tokens (if any); the Decisions API has none.
    reasoning = 0 if "answers" in raw else (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
    return Usage(
        requests=1,
        input_tokens=u.get("input_tokens", u.get("prompt_tokens")),
        output_tokens=u.get("output_tokens", u.get("completion_tokens")),
        reasoning_tokens=reasoning,
        cost_usd=u.get("cost"),
    )


class OpenRouterCropper(BaseCropper):
    """
    Base class. Subclasses implement
      choose(image, name, post) -> ((x, y, side, side), or None if the answer wasn't usable; details)
    sending their requests with `post(url, body) -> response JSON`.

    `transport(url, body)` sends each request; by default it's `post_json` with the
    config's [openrouter] key.
    """

    MODEL = None  # each subclass's default model
    concurrency = 8

    def __init__(self, config=None, model=None, transport=None):
        self.model = model or self.MODEL
        api_key = config.get("openrouter", "key", fallback=None) if config is not None else None
        self.transport = transport or partial(post_json, api_key=api_key)

    def crop_with_details(self, image_url, image_path, name=None):
        """The centred largest square, with details["fallback"], if the answer wasn't usable."""
        with Image.open(image_path) as image:
            image = image.convert("RGB")
        responses = []

        def post(url, body):
            raw = self.transport(url, body)
            responses.append(raw)
            return raw

        box, details = self.choose(image, name or "an organism", post)
        usage = reduce(add, map(response_usage, responses)) if responses else Usage()
        if box is None:
            return CropResult(CropBox(*centre_square(*image.size)), {**details, "fallback": True}, usage)
        return CropResult(CropBox(*box), details, usage)
