import os
import shutil
import types
import urllib.request
from unittest import mock
from oz_tree_build._OZglobals import src_flags
from oz_tree_build.utilities.db_helper import (
    connect_to_database,
    delete_all_by_ott,
    get_next_src_id_for_src,
)
from oz_tree_build.images_and_vernaculars import get_wiki_images


db_context = connect_to_database()

# Maps URLs to the JSON responses that should be returned
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


def get_command_arguments(subcommand, ott_or_taxon, image, rating):
    return types.SimpleNamespace(
        config_file=None,
        output_dir=None,
        subcommand=subcommand,
        ott_or_taxon=ott_or_taxon,
        image=image,
        rating=rating,
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
def image_test_helper(image, rating, *args):
    # Delete the test rows before starting the test.
    # We don't delete them at the end, because we want to see the results manually.
    delete_all_by_ott(db_context, "ordered_leaves", ott)
    delete_all_by_ott(db_context, "images_by_ott", ott)
    delete_all_by_ott(db_context, "vernacular_by_ott", ott)

    # Insert a leaf to set up the mapping between the ott and the wikidata id
    db_context.execute(
        "INSERT INTO ordered_leaves (parent, real_parent, name, ott, wikidata) VALUES (0, 0, {0}, {0}, {0});",
        ("Panthera leo", ott, qid),
    )

    # Note that the image src should be onezoom_bespoke if a bespoke image is used
    src = src_flags["onezoom_bespoke"] if image else src_flags["wiki"]

    # Insert a dummy image to test that it gets deleted in the wiki case, and kept in the bespoke case
    src_id = get_next_src_id_for_src(db_context, src)
    db_context.execute(
        "INSERT INTO images_by_ott (ott, src, src_id, url, rating, best_any, best_verified, best_pd, overall_best_any, overall_best_verified, overall_best_pd) VALUES ({0}, {0}, {0}, {0}, 1234, 1, 1, 1, 1, 1, 1);",
        (ott, src, src_id, "http://example.com/dummy.jpg"),
    )

    db_context.db_connection.commit()

    # Call the method that we want to test
    get_wiki_images.process_args(get_command_arguments("leaf", ott, image, rating))

    rows = db_context.fetchall(
        "SELECT ott, src, src_id, rating, overall_best_any FROM images_by_ott WHERE ott={0} ORDER BY id desc;",
        ott,
    )

    # There should only be one image in the database in wiki mode (since we delete first),
    # and two in bespoke mode
    assert len(rows) == 1 if src == src_flags["wiki"] else 2

    # Check the image details
    # src_id should be one more than the test row in the bespoke case, and the qid in the wiki case
    assert rows[0] == (
        int(ott),
        src,
        src_id + 1 if src == src_flags["onezoom_bespoke"] else int(qid),
        rating if rating else 35000,
        1,
    )

    # In the bespoke case, the call to process_image_bits at the end of get_wiki_images should have
    # set the overall_best_any bit to 0 for the dummy image (from its original 1 when we added it)
    if src == src_flags["onezoom_bespoke"]:
        assert rows[1][4] == 0

    # Check the vernacular names
    rows = db_context.fetchall(
        "SELECT ott, vernacular, lang_primary FROM vernacular_by_ott WHERE ott={0} ORDER BY id;",
        ott,
    )

    assert len(rows) == 4
    assert rows == (
        (int(ott), "Lion", "en"),
        (int(ott), "African Lion", "en"),
        (int(ott), "Lion", "fr"),
        (int(ott), "Lion d'Afrique", "fr"),
    )


def test_get_leaf_default_image():
    image_test_helper(None, None)


def test_get_leaf_bespoke_image():
    image_test_helper("SecondLionImage.jpg", 42000)
