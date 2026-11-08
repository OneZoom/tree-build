"""
Crop to the largest square, slid along the long edge to cover the most of a
salient-object mask from rembg. Needs the `saliency` extra (pip install
".[saliency]"); the model weights are downloaded to ~/.u2net on first use.
"""

from PIL import Image

from .base import BaseCropper, CropResult
from .geometry import CropBox

_sessions = {}


def mask_image(image, model="u2net"):
    """rembg's salient-object mask for a PIL image, as a greyscale PIL image."""
    # Imported here so the rest of image_cropping works without the optional dependencies.
    import rembg

    if model not in _sessions:
        _sessions[model] = rembg.new_session(model)
    return rembg.remove(image.convert("RGB"), session=_sessions[model], only_mask=True).convert("L")


def mask_array(mask):
    """A greyscale PIL mask as a numpy array of floats in [0, 1]."""
    import numpy as np

    return np.asarray(mask.convert("L"), dtype=np.float64) / 255


def best_window(profile, side):
    """Start of the length-`side` window with the largest sum; ties go to the one nearest the centre."""
    import numpy as np

    cumulative = np.concatenate([[0.0], np.cumsum(profile)])
    sums = cumulative[side:] - cumulative[:-side]
    candidates = np.flatnonzero(sums >= sums.max() - 1e-9 * max(sums.max(), 1.0))
    middle = (len(profile) - side) / 2
    return int(candidates[np.argmin(np.abs(candidates - middle))])


def square_from_mask(mask):
    """(x, y, side, side) of the largest square covering the most of `mask` (a 2D array)."""
    h, w = mask.shape
    short = min(w, h)
    if w >= h:
        return best_window(mask.sum(axis=0), short), 0, short, short
    return 0, best_window(mask.sum(axis=1), short), short, short


class SaliencyImageCropper(BaseCropper):
    def __init__(self, config=None, model="u2net"):
        self.model = model

    def crop_with_details(self, image_url, image_path, name=None):
        with Image.open(image_path) as image:
            return CropResult(CropBox(*square_from_mask(mask_array(mask_image(image, self.model)))))
