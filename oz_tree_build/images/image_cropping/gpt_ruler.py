"""
Crop by asking an LLM (by default OpenAI's GPT-5 nano, via OpenRouter) where the most
recognisable part of the organism is, on a 0-100 ruler along the image's long edge;
the largest square is centred there. Needs reasoning effort "low": with "minimal",
GPT-5 nano answers ~50 regardless of the image.
"""

import re

from PIL import Image, ImageDraw, ImageFont

from .geometry import square_at
from .openrouter import CHAT_URL, OpenRouterCropper, data_url, jpeg_bytes, scaled

LONG_SIDE = 512  # the picture's long side, before the ruler is added
REASONING_EFFORT = "low"
FOCUS = "the centre of the most recognisable part of the organism (for example an animal's head, or a plant's flowers)"
RULER_MARKS = list(range(0, 101, 10))


def axis_words(w, h):
    """(start edge, end edge, axis) for the direction the square can slide."""
    return ("left", "right", "horizontal") if w >= h else ("top", "bottom", "vertical")


def ruler_picture(image, long_side):
    """The whole image with a 0-100 ruler along its long edge."""
    w, h = image.size
    ov = scaled(image.convert("RGB"), long_side)
    band = 28
    canvas = Image.new("RGB", (ov.width, ov.height + band) if w >= h else (ov.width + band, ov.height), (255, 255, 255))
    canvas.paste(ov, (0, 0))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=14)
    for mark in RULER_MARKS:
        if w >= h:
            x = round(mark / 100 * (ov.width - 1))
            draw.line([x, ov.height, x, ov.height + 8], fill=(0, 0, 0), width=2)
            draw.text((min(max(x - 8, 0), ov.width - 24), ov.height + 9), str(mark), fill=(0, 0, 0), font=font)
        else:
            y = round(mark / 100 * (ov.height - 1))
            draw.line([ov.width, y, ov.width + 8, y], fill=(0, 0, 0), width=2)
            draw.text((ov.width + 9, min(max(y - 7, 0), ov.height - 16)), str(mark), fill=(0, 0, 0), font=font)
    return canvas


def ruler_prompt(name, w, h):
    lo, hi, axis = axis_words(w, h)
    return (
        f"This image shows {name}. It will be cropped to a square thumbnail for OneZoom, an interactive tree of life; "
        f"the square spans the full {'height' if w >= h else 'width'} and can slide {axis}ly. "
        f"Where is {FOCUS}? Use the ruler along the edge. "
        f"Answer with a single number from 0 ({lo} edge) to 100 ({hi} edge): its {axis} position from the {lo} edge."
    )


class GptRulerCropper(OpenRouterCropper):
    MODEL = "openai/gpt-5-nano"

    def choose(self, image, name, post):
        w, h = image.size
        jpeg = jpeg_bytes(ruler_picture(image, LONG_SIDE))
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": ruler_prompt(name, w, h)},
                        {"type": "image_url", "image_url": {"url": data_url(jpeg)}},
                    ],
                }
            ],
            "max_tokens": 4000,
            "usage": {"include": True},
            "reasoning": {"effort": REASONING_EFFORT},
        }
        raw = post(CHAT_URL, body)
        content = ((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", content) if 0 <= float(x) <= 100]
        if not nums:
            return None, {}
        return square_at(w, h, nums[-1] / 100), {}
