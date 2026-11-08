"""
Crop using boxes from TypeSafe's Jev decision model, via OpenRouter's Decisions API.

JevBoxCropper centres the largest square on Jev's box round the organism's most
recognisable part. JevTwoPhaseCropper asks for the whole organism first; if it's
longer than the square, it asks again for the head (or most recognisable part) in a
crop round the organism, and places the square with geometry.square_around.

Jev rejects pictures whose short side is below roughly 280-290px or that are more
elongated than about 3.8:1 ("Invalid image dimensions"), hence MIN_SHORT_SIDE and
MAX_CROP_ASPECT.
"""

from .geometry import centre_along_long_edge, square_around, square_at
from .openrouter import OpenRouterCropper, decide_box, jpeg_bytes, scaled

JEV_MODEL = "typesafe/jev-1.14"
MIN_SHORT_SIDE = 320  # pictures are scaled up to at least this short side
LONG_SIDE = 768  # JevBoxCropper's picture; the largest JevTwoPhaseCropper's head crop is sent at
PHASE1_LONG_SIDE = 512  # JevTwoPhaseCropper's whole-image picture, for the organism box
ORGANISM_PAD = 0.1  # the head crop is the organism box padded by this much of its size each side...
MAX_CROP_ASPECT = 3.0  # ...and widened along its short side to at most this aspect ratio
HEAD_MARGIN = 0.01  # how much of the square's side to keep between the head and the square's edge


def box_prompt(name):
    """(state text, box instructions) for JevBoxCropper."""
    return (
        f"This image shows {name}. Find the most recognisable part of the organism, the part a thumbnail should "
        "centre on: for an animal, its head; for a plant, its flowers or fruit or the most distinctive part; "
        "otherwise the organism itself. If there are several, choose the clearest one.",
        "Box the part the thumbnail should centre on.",
    )


def organism_prompt(name):
    """(state text, box instructions) for JevTwoPhaseCropper's first request."""
    return (
        f"This image shows {name}.",
        f"Box the whole {name}. If there are other organisms present, box the one in question. "
        "If there are multiple of the organism, box the most beautiful and complete one. ",
    )


def head_prompt(name):
    """(state text, box instructions) for JevTwoPhaseCropper's second request. The examples make the box tighter."""
    return (
        f"This is a crop of a picture of {name}.",
        "Box only the head, tightly. For example: a fish from the snout to the back of the gill cover; a bird, "
        "the head above the neck; an insect or spider, the head and the bases of its antennae; a snake or "
        "lizard, just the head. If it is a flowering plant, box its flower or fruit. "
        "If it has no head (a plant, fungus, shell, colony...), box only its most "
        "distinctive part.",
    )


class JevBoxCropper(OpenRouterCropper):
    MODEL = JEV_MODEL

    def choose(self, image, name, post):
        text, instructions = box_prompt(name)
        jpeg = jpeg_bytes(scaled(image, LONG_SIDE, MIN_SHORT_SIDE))
        box = decide_box(post, self.model, jpeg, text, instructions, "focus")
        if box is None:
            return None, {}
        return square_at(*image.size, centre_along_long_edge(box, *image.size)), {"boxes": {"head": box}}


class JevTwoPhaseCropper(OpenRouterCropper):
    """details: "boxes" (organism, and head if asked for) and "head_request_skipped"."""

    MODEL = JEV_MODEL

    def choose(self, image, name, post):
        w, h = image.size
        text, instructions = organism_prompt(name)
        jpeg1 = jpeg_bytes(scaled(image, PHASE1_LONG_SIDE, MIN_SHORT_SIDE))
        organism = decide_box(post, self.model, jpeg1, text, instructions, "box")
        if organism is None:
            return None, {}
        details = {"boxes": {"organism": organism}, "head_request_skipped": False}
        organism_square = square_at(w, h, centre_along_long_edge(organism, w, h))
        # If the whole organism fits in the square, the square just centres on it and the head can't change that.
        extent = (organism["right"] - organism["left"]) * w if w >= h else (organism["bottom"] - organism["top"]) * h
        if extent <= min(w, h):
            details["head_request_skipped"] = True
            return organism_square, details

        region = head_region(organism, w, h)
        px = tuple(round(region[k] * scale) for k, scale in (("left", w), ("top", h), ("right", w), ("bottom", h)))
        if px[2] - px[0] < 2 or px[3] - px[1] < 2:
            return organism_square, details
        crop = image.crop(px)
        text, instructions = head_prompt(name)
        # Don't upscale the crop beyond its own pixels, except to meet Jev's minimum short side.
        jpeg2 = jpeg_bytes(scaled(crop, min(LONG_SIDE, max(crop.size)), MIN_SHORT_SIDE))
        focus = decide_box(post, self.model, jpeg2, text, instructions, "box")
        if focus is None:
            return organism_square, details
        cw, ch = (px[2] - px[0]) / w, (px[3] - px[1]) / h
        head = {
            "left": px[0] / w + focus["left"] * cw,
            "right": px[0] / w + focus["right"] * cw,
            "top": px[1] / h + focus["top"] * ch,
            "bottom": px[1] / h + focus["bottom"] * ch,
        }
        details["boxes"]["head"] = head
        return square_around(w, h, head, organism, HEAD_MARGIN), details


def head_region(organism, w, h):
    """The organism box padded each side, then widened along its short side to at most MAX_CROP_ASPECT."""
    pad = ORGANISM_PAD
    bw, bh = organism["right"] - organism["left"], organism["bottom"] - organism["top"]
    region = {
        "left": max(0.0, organism["left"] - pad * bw),
        "right": min(1.0, organism["right"] + pad * bw),
        "top": max(0.0, organism["top"] - pad * bh),
        "bottom": min(1.0, organism["bottom"] + pad * bh),
    }
    max_aspect = max(MAX_CROP_ASPECT, max(w, h) / min(w, h))
    rw, rh = (region["right"] - region["left"]) * w, (region["bottom"] - region["top"]) * h
    if rw > max_aspect * rh:
        grow = (rw / max_aspect - rh) / h
        top = min(max(0.0, region["top"] - grow / 2), max(0.0, 1.0 - (region["bottom"] - region["top"] + grow)))
        region["top"], region["bottom"] = top, min(1.0, top + region["bottom"] - region["top"] + grow)
    elif rh > max_aspect * rw:
        grow = (rh / max_aspect - rw) / w
        left = min(max(0.0, region["left"] - grow / 2), max(0.0, 1.0 - (region["right"] - region["left"] + grow)))
        region["left"], region["right"] = left, min(1.0, left + region["right"] - region["left"] + grow)
    return region
