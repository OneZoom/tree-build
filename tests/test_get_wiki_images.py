import os
import shutil
import types
import urllib.request
from unittest import mock
from oz_tree_build._OZglobals import src_flags
from oz_tree_build.utilities.db_helper import connect_to_database
from oz_tree_build.images_and_vernaculars import get_wiki_images
from tests.db_test_helpers import delete_all_by_ott


db_context = connect_to_database()
mocked_requests = {}


# Mock the requests.get function
def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code
            self.text = ""

        def json(self):
            return self.json_data

    if args[0] in mocked_requests:
        return MockResponse(mocked_requests[args[0]], 200)

    return MockResponse(None, 404)


# Download an arbitrary test image in the tmp folder to use in the tests
temp_image_path = "/tmp/mocked_urlretrieve_image.jpg"
if not os.path.exists(temp_image_path):
    image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Lion_waiting_in_Namibia.jpg/500px-Lion_waiting_in_Namibia.jpg"
    urllib.request.urlretrieve(image_url, temp_image_path)


def mocked_urlretrieve(*args, **kwargs):
    # Instead of actually downloading the image, we just copy our test image to the destination
    shutil.copyfile(temp_image_path, args[1])


# Mock the Azure Vision API smart crop response
def mocked_analyze_from_url(*args, **kwargs):
    return types.SimpleNamespace(
        smart_crops=types.SimpleNamespace(
            list=[
                types.SimpleNamespace(
                    bounding_box=types.SimpleNamespace(
                        x=50, y=75, width=300, height=300
                    )
                )
            ]
        )
    )


def build_wikidata_entities(qid, images, vernaculars):
    entities = {
        "entities": {
            qid: {
                "claims": {"P18": [], "P1843": []},
            }
        }
    }

    for image in images:
        entities["entities"][qid]["claims"]["P18"].append(
            {
                "mainsnak": {
                    "datavalue": {
                        "value": image["name"],
                    },
                },
                "rank": image["rank"],
            }
        )

    for vernacular in vernaculars:
        entities["entities"][qid]["claims"]["P1843"].append(
            {
                "mainsnak": {
                    "datavalue": {
                        "value": {
                            "language": vernacular["language"],
                            "text": vernacular["name"],
                        },
                    },
                },
                "rank": vernacular["rank"],
            }
        )

    return entities


def get_command_arguments(subcommand, ott_or_taxon, image):
    return types.SimpleNamespace(
        config_file=None,
        output_dir=None,
        subcommand=subcommand,
        ott_or_taxon=ott_or_taxon,
        image=image,
        rating=None,
        skip_images=None,
    )


def patch_all(f):
    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("urllib.request.urlretrieve", side_effect=mocked_urlretrieve)
    @mock.patch(
        "azure.ai.vision.imageanalysis.ImageAnalysisClient.analyze_from_url",
        side_effect=mocked_analyze_from_url,
    )
    def functor(*args, **kwargs):
        return f(*args, **kwargs)

    return functor


ott = "-777"
qid = "7777777"

mocked_requests[
    f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q{qid}&format=json"
] = build_wikidata_entities(
    f"Q{qid}",
    [
        {"name": "FirstLionImage.jpg", "rank": "normal"},
        {"name": "SecondLionImage.jpg", "rank": "preferred"},
    ],
    [
        {"name": "Lion", "language": "en", "rank": "normal"},
        {"name": "Lion", "language": "fr", "rank": "normal"},
        {"name": "African Lion", "language": "en", "rank": "preferred"},
        {"name": "Lion d'Afrique", "language": "fr", "rank": "normal"},
    ],
)

mocked_requests[
    "https://api.wikimedia.org/w/api.php?action=query&prop=imageinfo&iiprop=extmetadata&titles=File%3aSecondLionImage.jpg&format=json&iiextmetadatafilter=License|LicenseUrl|Artist"
] = {
    "query": {
        "pages": {
            "-1": {
                "title": "File:Blah.jpg",
                "imageinfo": [
                    {
                        "extmetadata": {
                            "License": {"value": "cc0"},
                            "LicenseUrl": {
                                "value": "https://creativecommons.org/publicdomain/zero/1.0/"
                            },
                            "Artist": {"value": "John Doe"},
                        }
                    }
                ],
            }
        }
    }
}

mocked_requests[
    "https://api.wikimedia.org/core/v1/commons/file/SecondLionImage.jpg"
] = {
    "preferred": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/7/73/SecondLionImage.jpg"
    }
}


@patch_all
def image_test_helper(image, *args):
    # Delete the test rows before starting the test.
    # We don't delete them at the end, because we want to see the results manually.
    delete_all_by_ott(db_context, "ordered_leaves", ott)
    delete_all_by_ott(db_context, "images_by_ott", ott)
    delete_all_by_ott(db_context, "vernacular_by_ott", ott)

    # Insert this ott into the ordered_leaves table
    db_context.execute(
        "INSERT INTO OneZoom.ordered_leaves (parent, real_parent, name, ott, wikidata) VALUES (0, 0, {0}, {0}, {0});",
        ("qqq", ott, qid),
    )
    db_context.db_connection.commit()

    get_wiki_images.process_args(get_command_arguments("leaf", ott, image))

    sql = "SELECT ott, src, src_id FROM images_by_ott WHERE ott={0} ORDER BY id;"
    db_context.execute(sql, ott)
    rows = db_context.db_curs.fetchall()

    # There should only be one image in the database
    assert len(rows) == 1

    # Check the image details
    # Note that the src_id should be onezoom_bespoke if there is an image
    assert rows[0] == (
        int(ott),
        src_flags["onezoom_bespoke"] if image else src_flags["wiki"],
        int(qid),
    )


def test_get_leaf_default_image(*args):
    image_test_helper(None)


def test_get_leaf_bespoke_image(*args):
    image_test_helper("SecondLionImage.jpg")
