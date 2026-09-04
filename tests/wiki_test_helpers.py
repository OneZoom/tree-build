from types import SimpleNamespace
from unittest import mock

from oz_tree_build.images import get_wiki_images
from oz_tree_build.images.get_wiki_images import COMMONS_THUMB_WIDTH
from oz_tree_build.utilities.db_helper import delete_all_by_ott

MOCK_UPLOAD_DIR = "https://upload.wikimedia.org/wikipedia/commons/not/a/real/"

# These need to be real images to make the --real-apis mode work
first_lion_image_name = "Okonjima_Lioness.jpg"
second_lion_image_name = "Lioness_12.jpg"

# Bytes for tiny JPEG
TINY_JPEG_HEAD = bytes.fromhex(
    "".join(
        """
ffd8 ffe0 0010 4a46 4946 0001 0101 012c
012c 0000 ffdb 0043 00ff ffff ffff ffff
ffff ffff ffff ffff ffff ffff ffff ffff
ffff ffff ffff ffff ffff ffff ffff ffff
ffff ffff ffff ffff ffff ffff ffff ffff
ffff ffff ffff ffff ffff db00 4301 ffff
ffff ffff ffff ffff ffff ffff ffff ffff
ffff ffff ffff ffff ffff ffff ffff ffff
ffff ffff ffff ffff ffff ffff ffff ffff
ffff ffff ffff ffff ffff ffff ffff ffc0
0011 0801 f401 f403 0111 0002 1101 0311
01ff c400 1500 0101 0000 0000 0000 0000
0000 0000 0000 0003 ffc4 0014 1001 0000
0000 0000 0000 0000 0000 0000 0000 ffc4
0014 0101 0000 0000 0000 0000 0000 0000
0000 0000 ffc4 0014 1101 0000 0000 0000
0000 0000 0000 0000 0000 ffda 000c 0301
0002 1103 1100 3f00 a000 0000 0000 0000
""".split()
    )
)
TINY_JPEG_FOOT = bytes.fromhex(
    "".join(
        """
003f ffd9
""".split()
    )
)
TINY_JPEG = TINY_JPEG_HEAD + b"\x00" * (3260 - len(TINY_JPEG_HEAD) - len(TINY_JPEG_FOOT)) + TINY_JPEG_FOOT


class MockResponse:
    def __init__(self, status_code, json_data=None, content=None):
        self.status_code = status_code
        self.json_data = json_data
        self.text = ""
        self.content = content

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code != 200:
            raise ValueError("status = %d" % self.status_code)

    def iter_content(self, chunk_size):
        return [self.content]  # NB: Ignoring chunk size


class RemoteAPIs:
    """
    Use the lion as a test case
    """

    # Commons page id returned by the mocked imageinfo API. Wiki images are saved
    # under this id, not the taxon QID.
    mock_page_id = 12345

    def add_mocked_request(self, url, querystring=None, *, response):
        if querystring is not None:
            url += "?" + querystring
        self.mocked_requests[url] = response

    def __init__(self, mock_qid):
        self.mock_qid = mock_qid
        self.true_qid = 140
        self.mocked_requests = {}  # Maps URLs to JSON responses to return
        self.license_urls = {
            "cc0": "https://creativecommons.org/publicdomain/zero/1.0/",
            "flickr_commons": "https://www.flickr.com/commons/usage/",
            "lal": "http://artlibre.org/licence/lal/en",
            "cc-by-3.0": "https://creativecommons.org/licenses/by/3.0",
        }

        self.add_mocked_request(
            **self.wikidata_response(
                image_data=[
                    {"name": first_lion_image_name, "rank": "normal"},
                    {"name": second_lion_image_name, "rank": "preferred"},
                ],
                vernacular_data=[
                    {"name": "Löwe", "language": "de", "rank": "normal"},  # -> preferred
                    {"name": "Lion", "language": "en", "rank": "normal"},
                    {"name": "Lion", "language": "fr", "rank": "preferred"},
                    {"name": "African Lion", "language": "en", "rank": "preferred"},
                    # Next should save as not preferred, as there are 2 fr preferred
                    {"name": "Lion d'Afrique", "language": "fr", "rank": "preferred"},
                ],
            ),
        )
        self.expected_mock_vn_order = (  # by preferred and then lang
            ("Löwe", "de"),  # test with accents
            ("African Lion", "en"),
            ("Lion", "en"),
            ("Lion", "fr"),
            ("Lion d'Afrique", "fr"),
        )

        self.add_mocked_request(**self.wikimedia_response(second_lion_image_name))
        self.add_mocked_request(**self.wikimedia_response("NoArtist.jpg", artist=None))
        self.add_mocked_request(**self.wikimedia_response("PublicDomain.jpg", licence="pd-NOOA"))
        self.add_mocked_request(**self.wikimedia_response("CC-BY3.jpg", licence="cc-by-3.0"))
        self.add_mocked_request(**self.wikimedia_response("Flickr.jpg", licence="flickr_commons"))
        self.add_mocked_request(**self.wikimedia_response("BadLicence.jpg", "GPL"))
        self.add_mocked_request(**self.wikimedia_response("NotAnImage.html"))

    # Mock the requests.get function
    def mocked_requests_get(self, *args, **kwargs):
        url = args[0]
        if url.startswith(MOCK_UPLOAD_DIR):
            content = None
            if url.endswith(".jpg"):
                content = TINY_JPEG
            elif url.endswith(".html"):
                content = b"<html>not an image</html>"
            return MockResponse(200, None, content)
        if url in self.mocked_requests:
            return MockResponse(200, self.mocked_requests[url])
        return MockResponse(404)

    # Mock the Azure Vision API smart crop response
    def mocked_analyze_from_url(self, *args, **kwargs):
        return SimpleNamespace(
            smart_crops=SimpleNamespace(
                list=[SimpleNamespace(bounding_box=SimpleNamespace(x=50, y=75, width=300, height=300))]
            )
        )

    def wikimedia_response(self, image_name, licence="cc0", artist="John Doe"):
        # NB use british spelling of licence to avoid shadowing python builtin
        url = (
            "https://commons.wikimedia.org/w/api.php"
            f"?action=query&titles=File%3a{image_name}&format=json&prop=imageinfo"
            f"&iiprop=url|extmetadata&iiurlwidth={COMMONS_THUMB_WIDTH}"
            "&iiextmetadatafilter=License|LicenseShortName|LicenseUrl|Artist"
        )
        download_url = MOCK_UPLOAD_DIR + image_name
        response = {
            "query": {
                "pages": {
                    str(self.mock_page_id): {
                        "pageid": self.mock_page_id,
                        "title": f"File:{image_name}",
                        "imageinfo": [
                            {
                                "extmetadata": {},
                                "thumburl": download_url,
                                "url": download_url,
                            }
                        ],
                    }
                }
            }
        }
        extmetadata = response["query"]["pages"][str(self.mock_page_id)]["imageinfo"][0]["extmetadata"]
        if artist is not None:
            extmetadata["Artist"] = {"value": artist}
        if licence in self.license_urls:
            extmetadata["License"] = {"value": licence}
            extmetadata["LicenseUrl"] = {"value": self.license_urls[licence]}
        else:
            extmetadata["License"] = {"value": licence}
        return {"url": url, "response": response}

    def wikidata_response(self, image_data, vernacular_data):
        qid = f"Q{self.mock_qid}"
        url = "https://www.wikidata.org/w/api.php"
        querystring = f"action=wbgetentities&ids={qid}&format=json"
        response = {}
        images = []
        vernaculars = []
        for img in image_data:
            images.append(
                {
                    "mainsnak": {
                        "datavalue": {
                            "value": img["name"],
                        },
                    },
                    "rank": img["rank"],
                }
            )
        for vn in vernacular_data:
            vernaculars.append(
                {
                    "mainsnak": {
                        "datavalue": {
                            "value": {"language": vn["language"], "text": vn["name"]},
                        },
                    },
                    "rank": vn["rank"],
                }
            )
        response["entities"] = {qid: {"claims": {"P18": images, "P1843": vernaculars}}}

        return {"url": url, "querystring": querystring, "response": response}

    def mock_patch_all_web_request_methods(self, f):
        @mock.patch("requests.get", side_effect=self.mocked_requests_get)
        @mock.patch(
            "azure.ai.vision.imageanalysis.ImageAnalysisClient.analyze_from_url",
            side_effect=self.mocked_analyze_from_url,
        )
        def functor(*args, **kwargs):
            return f(*args, **kwargs)

        return functor


def delete_rows(db, ott):
    delete_all_by_ott(db, "images_by_ott", ott)
    delete_all_by_ott(db, "vernacular_by_ott", ott)
    # The negative OTT should have been added to the end of the ordered_leaves table
    # and so adding and removing it shouldn't mess up the nested set structure, we hope
    delete_all_by_ott(db, "ordered_leaves", ott)


def default_rating(image=None):
    if image is None:
        return get_wiki_images.default_wiki_image_rating
    return get_wiki_images.bespoke_wiki_image_rating
