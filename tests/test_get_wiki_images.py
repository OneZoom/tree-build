import os
import pytest
import shutil
import types
import urllib.request
from unittest import mock

from PIL import Image

from oz_tree_build._OZglobals import src_flags
from oz_tree_build.utilities.db_helper import (
    delete_all_by_ott,
    get_next_src_id_for_src,
    placeholder,
)
from oz_tree_build.images_and_vernaculars import get_wiki_images

# Maps URLs to the JSON responses that should be returned
mocked_requests = {}

# Download an arbitrary test image in the tmp folder to use in the tests
temp_image_path = "/tmp/mocked_urlretrieve_image.jpg"
if not os.path.exists(temp_image_path):
    image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Lion_waiting_in_Namibia.jpg/500px-Lion_waiting_in_Namibia.jpg"
    urllib.request.urlretrieve(image_url, temp_image_path)

# Mock the requests.get function
def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code
            self.text = ""

        def json(self):
            return self.json_data
        
        @property
        def content(self):
            with open(temp_image_path, "rb") as f:
                return f.read()

    if args[0] in mocked_requests:
        return MockResponse(mocked_requests[args[0]], 200)

    return MockResponse(None, 404)



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


def get_command_arguments(subcommand, ott_or_taxon, image, rating, config_file):
    return types.SimpleNamespace(
        output_dir=None,
        subcommand=subcommand,
        ott_or_taxon=ott_or_taxon,
        image=image,
        rating=rating,
        skip_images=None,
        config_file=config_file,
    )


def patch_all_web_request_methods(f):
    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("urllib.request.urlretrieve", side_effect=mocked_urlretrieve)
    @mock.patch(
        "azure.ai.vision.imageanalysis.ImageAnalysisClient.analyze_from_url",
        side_effect=mocked_analyze_from_url,
    )
    def functor(*args, **kwargs):
        return f(*args, **kwargs)

    return functor


qid = 7777777

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
        # This is the preferred image size, not the preferred image itself
        "url": "https://upload.wikimedia.org/wikipedia/commons/7/73/SecondLionImage.jpg"
    }
}

def delete_rows(db, ott):
    delete_all_by_ott(db, "images_by_ott", ott)
    delete_all_by_ott(db, "vernacular_by_ott", ott)
    # The negative OTT should have been added to the end of the ordered_leaves table
    # and so adding and removing it shouldn't mess up the nested set structure, we hope
    delete_all_by_ott(db, "ordered_leaves", ott)

class TestFunctions:
    """
    Test calling the subfunctions
    """
    def test_get_image_crop_box(self):
        #assert get_wiki_images.get_image_crop_box("https://example.com/image.jpg") == {
        #    "x": 50,
        #    "y": 75,
        #    "width": 300,
        #    "height": 300,
        #}
        pass


class TestAPI:
    @patch_all_web_request_methods
    def verify_process_leaf(self, image, rating, *args):
        db = self.db
        ph = placeholder(db)
        sql = "SELECT src_id, rating FROM images_by_ott WHERE ott={0};"
        get_wiki_images.process_leaf(
            self.db, self.ott, output_dir=self.tmp_dir, skip_images=True
        )
        # Images skipped, so should have no row
        rows = self.db.executesql(sql.format(ph), (self.ott,))
        assert len(rows) == 0
        get_wiki_images.process_leaf(
            self.db, self.ott, rating=rating, output_dir=self.tmp_dir, skip_images=False
        )
        dir = os.path.join(self.tmp_dir, str(src_flags["wiki"]), str(qid)[-3:])
        # No crop, so should have taken the default size
        uncropped = os.path.join(dir, f"{qid}_uncropped.jpg")
        assert os.path.exists(uncropped)
        w, h = Image.open(uncropped).size
        assert (w, h) == Image.open(temp_image_path).size
        cropped = os.path.join(dir, f"{qid}.jpg")
        assert os.path.exists(cropped)
        assert Image.open(cropped).size == (300, 300)
        cropinfo = os.path.join(dir, f"{qid}_cropinfo.txt")
        assert os.path.exists(cropinfo)
        with open(cropinfo) as f:
            s = f.read()
            print(h>w, s)
            if h > w:
                assert s.startswith(f"0,")
                assert s.endswith(f",{w},{w}")
            else:    
                assert s.endswith(f",0,{h},{h}")

        rows = self.db.executesql(sql.format(ph), (self.ott,))
        assert len(rows) == 1
        assert rows[0] == (qid, 40123)

    def test_process_default_leaf(self, db, keep_rows, tmp_path):
        self.ott = "-551"
        self.db = db
        self.tmp_dir = tmp_path
        delete_rows(db, self.ott)
        db.executesql(
            "INSERT INTO ordered_leaves (parent, real_parent, name, ott, wikidata) "
            "VALUES (0, 0, {0}, {0}, {0});".format(placeholder(db)),
            ("Panthera leo", self.ott, qid),
        )
        self.verify_process_leaf(None, 40123)
        if not keep_rows:
            delete_rows(db, self.ott)

    def test_process_clade(self):
        pass


class TestCLI:
    def test_get_leaf_default_image(self, db, appconfig, keep_rows):
        self.db = db
        self.appconfig = appconfig
        self.ott = "-771"
        delete_rows(db, self.ott)
        self.verify_image_behavior(None, None)
        if not keep_rows:
            delete_rows(db, self.ott)

    def test_get_leaf_bespoke_image(self, db, appconfig, keep_rows):
        self.db = db
        self.appconfig = appconfig
        self.ott = "-772"
        delete_rows(db, self.ott)
        self.verify_image_behavior("SecondLionImage.jpg", 42000)
        if not keep_rows:
            delete_rows(db, self.ott)

    @patch_all_web_request_methods
    def verify_image_behavior(self, image, rating, *args):
        assert int(self.ott) < 0
        ph = placeholder(self.db)

        # Insert a leaf to set up the mapping between the ott and the wikidata id
        self.db._adapter.execute(
            "INSERT INTO ordered_leaves (parent, real_parent, name, ott, wikidata) "
            "VALUES (0, 0, {0}, {0}, {0});".format(ph),
            ("Panthera leo", self.ott, qid),
        )

        # Note that the image src should be onezoom_bespoke if a bespoke image is used
        src = src_flags["onezoom_bespoke"] if image else src_flags["wiki"]

        # Insert a dummy image to test that it gets deleted in the wiki case, and kept in the bespoke case
        src_id = get_next_src_id_for_src(self.db, src)
        self.db._adapter.execute(
            "INSERT INTO images_by_ott "
            "(ott, src, src_id, url, rating, best_any, best_verified, best_pd, overall_best_any, "
            "overall_best_verified, overall_best_pd) "
            "VALUES ({0}, {0}, {0}, {0}, 1234, 1, 1, 1, 1, 1, 1);".format(ph),
            (self.ott, src, src_id, "http://example.com/dummy.jpg"),
        )

        self.db.commit()

        # Call the method that we want to test
        get_wiki_images.process_args(get_command_arguments("leaf", self.ott, image, rating, self.appconfig))

        rows = self.db.executesql(
            f"SELECT ott, src, src_id, rating, overall_best_any FROM images_by_ott WHERE ott={ph} ORDER BY id desc;",
            (self.ott, ),
        )

        # There should only be one image in the database in wiki mode (since we delete first),
        # and two in bespoke mode
        assert len(rows) == 1 if src == src_flags["wiki"] else 2

        # Check the image details
        # src_id should be one more than the test row in the bespoke case, and the qid in the wiki case
        assert rows[0] == (
            int(self.ott),
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
        rows = self.db.executesql(
            f"SELECT ott, vernacular, lang_primary FROM vernacular_by_ott WHERE ott={ph} ORDER BY id;",
            (self.ott, ),
        )

        assert len(rows) == 4
        assert tuple(rows) == (
            (int(self.ott), "Lion", "en"),
            (int(self.ott), "African Lion", "en"),
            (int(self.ott), "Lion", "fr"),
            (int(self.ott), "Lion d'Afrique", "fr"),
        )
