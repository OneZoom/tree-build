"""
The cropper interface. Every cropper extends BaseCropper and implements
crop_with_details(image_url, image_path, name=None) -> CropResult: the crop, details
of how it was reached, and what it cost (Usage). crop() returns just the box.
"""

from dataclasses import dataclass, field

from .geometry import CropBox


def _add(a, b):
    return None if a is None or b is None else a + b


@dataclass(frozen=True)
class Usage:
    """What a crop cost. A None count or cost means the API didn't report it."""

    requests: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost_usd: float | None = 0.0
    cost_is_list_price: bool = False  # estimated from a price list rather than reported per request

    def __add__(self, other):
        return Usage(
            self.requests + other.requests,
            _add(self.input_tokens, other.input_tokens),
            _add(self.output_tokens, other.output_tokens),
            _add(self.reasoning_tokens, other.reasoning_tokens),
            _add(self.cost_usd, other.cost_usd),
            self.cost_is_list_price or other.cost_is_list_price,
        )


@dataclass(frozen=True)
class CropResult:
    """
    `details` may have "boxes" ({label: {left, right, top, bottom} fractions of the
    image}, e.g. what a model boxed) and boolean flags saying how the crop was reached
    (e.g. "fallback" when a model gave no usable answer).
    """

    box: CropBox
    details: dict = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)


class BaseCropper:
    """
    Every cropper is made with `config`, an appconfig ConfigParser (or None), for any
    keys or settings it needs. `transport` is the callable that makes a remote
    cropper's API calls (None for local ones); its arguments are JSON-serialisable or
    bytes, and it returns JSON. Replace it to change how calls are made, e.g. to cache
    them. `concurrency` is how many crops are worth running at once.
    """

    concurrency = 1
    transport = None

    def __init__(self, config=None):
        pass

    def crop_with_details(self, image_url, image_path, name=None) -> CropResult:
        raise NotImplementedError

    def crop(self, image_url, image_path, name=None) -> CropBox:
        return self.crop_with_details(image_url, image_path, name).box
