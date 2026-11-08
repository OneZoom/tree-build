"""
Ways of choosing a square crop for an image. Every cropper is a BaseCropper (see
base.py), with `crop(image_url, image_path, name=None)` returning a CropBox in pixels
of the uncropped image, and `crop_with_details` also returning how it got there and
what it cost: `image_url` is where the image can be fetched from (only Azure uses
it, and uploads the file at `image_path` if it's empty), and `name` is the species'
scientific name (only the OpenRouter-based ones use it, in their prompts).
`make_cropper(name, config)` builds one by name. See data/crop_experiment/README.md
for how they compare.
"""

from typing import Literal

from .azure import AzureImageCropper
from .base import BaseCropper, CropResult, Usage
from .centre import CenterImageCropper
from .geometry import CropBox
from .gpt_ruler import GptRulerCropper
from .jev import JevBoxCropper, JevTwoPhaseCropper
from .openrouter import OpenRouterCropper, OpenRouterError
from .saliency import SaliencyImageCropper

CropperName = Literal["centre", "saliency", "azure", "gpt-5-nano", "jev-box", "jev-two-phase"]

CROPPERS: dict[CropperName, type[BaseCropper]] = {
    "centre": CenterImageCropper,
    "saliency": SaliencyImageCropper,
    "azure": AzureImageCropper,
    "gpt-5-nano": GptRulerCropper,
    "jev-box": JevBoxCropper,
    "jev-two-phase": JevTwoPhaseCropper,
}


def make_cropper(name: CropperName, config=None) -> BaseCropper:
    """
    The cropper called `name` (a key of CROPPERS). `config` is an appconfig
    ConfigParser: Azure needs its [azure_vision] section, the OpenRouter-based croppers
    its [openrouter] key.
    """
    return CROPPERS[name](config)


__all__ = [
    "CROPPERS",
    "AzureImageCropper",
    "BaseCropper",
    "CenterImageCropper",
    "CropBox",
    "CropResult",
    "GptRulerCropper",
    "JevBoxCropper",
    "JevTwoPhaseCropper",
    "OpenRouterCropper",
    "OpenRouterError",
    "SaliencyImageCropper",
    "Usage",
    "make_cropper",
]
