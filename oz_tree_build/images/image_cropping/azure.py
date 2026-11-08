"""
Crop using the Azure AI Vision Image Analysis 4.0 smart-crops feature. Microsoft has
deprecated Image Analysis 4.0 and plans to retire it on 25 September 2028.
"""

import configparser
import logging
import sys
from pathlib import Path

from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential

from .base import BaseCropper, CropResult, Usage
from .geometry import CropBox

logger = logging.getLogger(Path(__file__).name)


def square_box(x, y, width, height):
    """
    Azure's "square" crops are often a pixel off (e.g. 606x605, from rounding), so
    trim the longer side to the shorter one. Shrinking keeps the box in bounds.
    """
    side = min(width, height)
    return CropBox(x, y, side, side)


class AzureImageCropper(BaseCropper):
    """
    `transport(image_url, image_bytes) -> {x, y, width, height}` makes the API call: Azure
    fetches `image_url`, or if that's empty, `image_bytes` are uploaded. `config` (an
    appconfig with an [azure_vision] section) is only needed to make real calls.
    """

    # List price per 1,000 calls
    # https://azure.microsoft.com/en-us/pricing/details/computer-vision/
    PRICE_PER_1000_CALLS_USD = 1.00
    concurrency = 4

    def __init__(self, config=None, transport=None):
        self.client = None if config is None else self._client(config)
        self.transport = transport or self.smart_crop

    @staticmethod
    def _client(config):
        try:
            azure_vision_endpoint = config.get("azure_vision", "endpoint")
            azure_vision_key = config.get("azure_vision", "key")
        except (configparser.NoSectionError, configparser.NoOptionError):
            logger.error("Azure Vision API key not found in config file")
            sys.exit()
        return ImageAnalysisClient(
            endpoint=azure_vision_endpoint,
            credential=AzureKeyCredential(azure_vision_key),
            # Retry throttling (429, honouring Retry-After) and server errors with backoff.
            retry_total=8,
            retry_backoff_factor=1.0,
            retry_backoff_max=60,
        )

    def smart_crop(self, image_url, image_bytes):
        """Azure's square smart crop for the image, as {x, y, width, height}."""
        if self.client is None:
            raise RuntimeError("AzureImageCropper needs a config with an [azure_vision] section to call Azure")
        options = {"visual_features": [VisualFeatures.SMART_CROPS], "smart_crops_aspect_ratios": [1.0]}
        # Disable logging around this call as it's too verbose
        logging.disable(logging.CRITICAL)
        try:
            if image_url:
                result = self.client.analyze_from_url(image_url, **options)
            else:
                result = self.client.analyze(image_bytes, **options)
        finally:
            logging.disable(logging.NOTSET)
        box = result.smart_crops.list[0].bounding_box
        return {"x": box.x, "y": box.y, "width": box.width, "height": box.height}

    def crop_with_details(self, image_url, image_path, name=None):
        if not image_url and not image_path:
            raise ValueError("Azure Vision API needs an image URL or file")
        image_bytes = None if image_url else Path(image_path).read_bytes()
        box = self.transport(image_url, image_bytes)
        usage = Usage(requests=1, cost_usd=self.PRICE_PER_1000_CALLS_USD / 1000, cost_is_list_price=True)
        return CropResult(square_box(**box), usage=usage)
