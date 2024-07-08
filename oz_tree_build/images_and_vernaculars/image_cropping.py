"""
Contains different classes for cropping images.
"""

import configparser
import logging
import sys
import types
from pathlib import Path

from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential
from PIL import Image

logger = logging.getLogger(Path(__file__).name)


class AzureImageCropper:
    def __init__(self, config):
        """
        Given a config object, return an Azure Image Analysis client.
        """
        try:
            azure_vision_endpoint = config.get("azure_vision", "endpoint")
            azure_vision_key = config.get("azure_vision", "key")
        except configparser.NoOptionError:
            logger.error("Azure Vision API key not found in config file")
            sys.exit()

        self.client = ImageAnalysisClient(
            endpoint=azure_vision_endpoint,
            credential=AzureKeyCredential(azure_vision_key),
        )

    def crop(self, image_url, image_path):
        """
        Get the crop box for an image using the Azure Vision API.
        """
        if not image_url:
            raise ValueError("Azure Vision API can only be used with URLs")

        result = self.client.analyze_from_url(
            image_url,
            visual_features=[VisualFeatures.SMART_CROPS],
            smart_crops_aspect_ratios=[1.0],
        )
        return result.smart_crops.list[0].bounding_box


class CenterImageCropper:
    def crop(self, image_url, image_path):
        """
        Get the crop box for an image by centering it.
        """
        img = Image.open(image_path)
        w, h = img.size
        square_dim = min(w, h)
        crop = ((w - square_dim) // 2, (h - square_dim) // 2, square_dim, square_dim)
        return types.SimpleNamespace(x=crop[0], y=crop[1], width=crop[2], height=crop[3])
