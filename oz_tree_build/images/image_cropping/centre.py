"""Crop to the largest square, centred."""

from PIL import Image

from .base import BaseCropper, CropResult
from .geometry import CropBox


def centre_square(w, h):
    """(x, y, side, side) of the largest square centred in a w x h image."""
    side = min(w, h)
    return (w - side) // 2, (h - side) // 2, side, side


class CenterImageCropper(BaseCropper):
    def crop_with_details(self, image_url, image_path, name=None):
        with Image.open(image_path) as img:
            return CropResult(CropBox(*centre_square(*img.size)))
