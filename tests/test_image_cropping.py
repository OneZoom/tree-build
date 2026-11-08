import pytest
from PIL import Image

from oz_tree_build.images.image_cropping import (
    AzureImageCropper,
    CenterImageCropper,
    CropBox,
    JevBoxCropper,
    JevTwoPhaseCropper,
)


@pytest.fixture()
def wide_image(tmp_path):
    path = tmp_path / "wide.jpg"
    Image.new("RGB", (900, 300), "white").save(path)
    return path


def decisions_post(*answers):
    """A stand-in transport that answers successive Decisions API requests with boxes."""
    sent = []

    def post(url, body):
        sent.append(body)
        box = answers[len(sent) - 1]
        key = next(iter(body["questions"]))
        return {"answers": {key: {"box": box} if box else {}}, "usage": {"input_tokens": 100, "cost": 0.001}}

    post.sent = sent
    return post


def test_centre_cropper(wide_image):
    assert CenterImageCropper().crop(None, wide_image) == CropBox(300, 0, 300, 300)


def test_jev_box_centres_the_square_on_the_box(wide_image):
    post = decisions_post({"left": 0.8, "right": 0.9, "top": 0.8, "bottom": 0.9})
    result = JevBoxCropper(transport=post).crop_with_details(None, wide_image)
    assert result.box == CropBox(600, 0, 300, 300)  # centred at x=765, clamped to the right edge


def test_jev_two_phase_skips_the_head_request_when_the_organism_fits(wide_image):
    post = decisions_post({"left": 0.1, "right": 0.3, "top": 0.2, "bottom": 0.8})
    result = JevTwoPhaseCropper(transport=post).crop_with_details(None, wide_image)
    assert len(post.sent) == 1
    assert result.box == CropBox(30, 0, 300, 300)  # centred on the organism (x=180)


def test_jev_two_phase_keeps_the_head_in(wide_image):
    organism = {"left": 0.0, "right": 1.0, "top": 0.2, "bottom": 0.8}
    head = {"left": 0.9, "right": 1.0, "top": 0.0, "bottom": 1.0}  # in the head request's crop
    post = decisions_post(organism, head)
    result = JevTwoPhaseCropper(transport=post).crop_with_details(None, wide_image)
    assert len(post.sent) == 2
    assert result.box.x + result.box.width >= 900 * result.details["boxes"]["head"]["right"] - 1


def test_openrouter_cropper_falls_back_to_the_centre(wide_image):
    result = JevBoxCropper(transport=decisions_post(None)).crop_with_details(None, wide_image)
    assert result.box == CropBox(300, 0, 300, 300)
    assert result.details["fallback"]


def test_azure_squares_its_box(wide_image):
    def transport(image_url, image_bytes):
        return {"x": 10, "y": 0, "width": 301, "height": 300}

    assert AzureImageCropper(transport=transport).crop(None, wide_image) == CropBox(10, 0, 300, 300)
