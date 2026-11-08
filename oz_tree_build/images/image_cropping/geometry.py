"""
Crop boxes, and placing the largest square (side = the image's short edge) along the
image's long edge. Fractional boxes are {left, right, top, bottom} fractions of the image.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CropBox:
    """A crop in pixels of the uncropped image."""

    x: int
    y: int
    width: int
    height: int

    def as_tuple(self):
        return self.x, self.y, self.width, self.height


def square_at(w, h, frac):
    """The largest square, centred at fraction `frac` along the long edge and clamped to the image."""
    short, long_ = min(w, h), max(w, h)
    pos = round(min(max(frac * long_ - short / 2, 0), long_ - short))
    return (pos, 0, short, short) if w >= h else (0, pos, short, short)


def centre_along_long_edge(box, w, h):
    """Where a fractional box's centre is along the long edge, as a fraction of it."""
    return (box["left"] + box["right"]) / 2 if w >= h else (box["top"] + box["bottom"]) / 2


def square_around(w, h, head, organism, head_margin):
    """
    The largest square that keeps `head` inside (with `head_margin` of the side to
    spare) and covers as much of `organism` as possible: if all of the organism fits
    it's centred, otherwise the square stays as close to centring the head as it can.
    If the head can't fit with its margin, the square is centred on the head.
    """
    keys = ("left", "right") if w >= h else ("top", "bottom")
    short, long_ = min(w, h), max(w, h)
    h0, h1 = (head[k] * long_ for k in keys)
    o0, o1 = (organism[k] * long_ for k in keys)
    margin = head_margin * short
    lo, hi = max(0, h1 + margin - short), min(long_ - short, h0 - margin)
    if lo > hi:
        return square_at(w, h, (h0 + h1) / 2 / long_)
    preferred = (o0 + o1 - short) / 2 if o1 - o0 <= short else (h0 + h1 - short) / 2
    positions = range(math.ceil(lo), math.floor(hi) + 1) or [round(lo)]
    overlap = {p: max(0.0, min(p + short, o1) - max(p, o0)) for p in positions}
    best = max(overlap.values())
    pos = min((p for p, v in overlap.items() if v >= best - 0.5), key=lambda p: abs(p - preferred))
    return (pos, 0, short, short) if w >= h else (0, pos, short, short)
