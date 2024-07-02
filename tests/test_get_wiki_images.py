import os
import pytest
import shutil
import urllib.request
from unittest import mock
from types import SimpleNamespace

from PIL import Image

from oz_tree_build._OZglobals import src_flags
from oz_tree_build.utilities.db_helper import (
    delete_all_by_ott,
    get_next_src_id_for_src,
    placeholder,
)
from oz_tree_build.images_and_vernaculars import get_wiki_images

class MockResponse:
    def __init__(self, status_code, json_data=None, content=None):
        self.status_code = status_code
        self.json_data = json_data
        self.text = ""
        self.content = content

    def json(self):
        return self.json_data
    
    


class RemoteAPIs:
    """
    Use the lion as a test case
    """
    cc0_url = "https://creativecommons.org/publicdomain/zero/1.0/"
    def add_mocked_request(self, url, querystring=None, *, response):
        if querystring is not None:
            url += "?" + querystring
        self.mocked_requests[url] = response

    def __init__(self, mock_qid):
        self.mock_qid = mock_qid
        self.true_qid = 140
        self.mocked_requests = {} # Maps URLs to the JSON responses that should be returned


        # Download an arbitrary test image in the tmp folder to use in the tests
        self.temp_image_path = "/tmp/mocked_urlretrieve_image.jpg"
        if not os.path.exists(self.temp_image_path):
            image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Lion_waiting_in_Namibia.jpg/500px-Lion_waiting_in_Namibia.jpg"
            urllib.request.urlretrieve(image_url, self.temp_image_path)
        with open(self.temp_image_path, "rb") as f:
            self.temp_image_content = f.read()

        self.add_mocked_request(
            "https://www.wikidata.org/w/api.php",
            f"action=wbgetentities&ids=Q{self.mock_qid}&format=json",
            response = self.build_wikidata_entities(
                image_data=[
                    {"name": "FirstLionImage.jpg", "rank": "normal"},
                    {"name": "SecondLionImage.jpg", "rank": "preferred"},
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

        self.add_mocked_request(
            "https://api.wikimedia.org/w/api.php",
            "action=query&prop=imageinfo&iiprop=extmetadata&titles=File%3aSecondLionImage.jpg"
            "&format=json&iiextmetadatafilter=License|LicenseUrl|Artist",
            response={
                "query": {
                    "pages": {
                        "-1": {
                            "title": "File:Blah.jpg",
                            "imageinfo": [
                                {
                                    "extmetadata": {
                                        "License": {"value": "cc0"},
                                        "LicenseUrl": {"value": self.cc0_url},
                                        "Artist": {"value": "John Doe"},
                                    }
                                }
                            ],
                        }
                    }
                }
            }
        )
        self.add_mocked_request(
            "https://api.wikimedia.org/core/v1/commons/file/SecondLionImage.jpg",
            response={
                "preferred": {  # NB: means preferred size of image, not which image is preferred
                    "url": "https://upload.wikimedia.org/wikipedia/commons/7/73/SecondLionImage.jpg"
                }
            }
        )

    # Mock the requests.get function
    def mocked_requests_get(self, *args, **kwargs):
        if args[0] in self.mocked_requests:
            content = self.temp_image_content if args[0].endswith(".jpg") else None
            return MockResponse(200, self.mocked_requests[args[0]], content)
        return MockResponse(404)

    def mocked_urlretrieve(self, *args, **kwargs):
        # Instead of actually downloading the image, we just copy our test image to the destination
        shutil.copyfile(self.temp_image_path, args[1])

    # Mock the Azure Vision API smart crop response
    def mocked_analyze_from_url(self, *args, **kwargs):
        return SimpleNamespace(
            smart_crops=SimpleNamespace(
                list=[
                    SimpleNamespace(
                        bounding_box=SimpleNamespace(x=50, y=75, width=300, height=300)
                    )
                ]
            )
        )

    def build_wikidata_entities(self, image_data, vernacular_data):
        qid = f"Q{self.mock_qid}"
        ret_val = {}
        images = []
        vernaculars = []
        for img in image_data:
            images.append({
                "mainsnak": {
                    "datavalue": {
                        "value": img["name"],
                    },
                },
                "rank": img["rank"],
            })
        for vn in vernacular_data:
            vernaculars.append({
                "mainsnak": {
                    "datavalue": {
                        "value": {"language": vn["language"], "text": vn["name"]},
                    },
                },
                "rank": vn["rank"],
            })

        ret_val["entities"] = {qid: {"claims": {"P18": images, "P1843": vernaculars}}}
        return ret_val


    def mock_patch_all_web_request_methods(self, f):
        @mock.patch("requests.get", side_effect=self.mocked_requests_get)
        @mock.patch("urllib.request.urlretrieve", side_effect=self.mocked_urlretrieve)
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

def get_command_arguments(subcommand, ott_or_taxa, image, rating, output_dir, config_file):
    return SimpleNamespace(
        subcommand=subcommand,
        ott_or_taxa=ott_or_taxa,
        image=image,
        rating=rating,
        skip_images=None,
        output_dir=output_dir,
        config_file=config_file,
    )

class TestFunctions:
    """
    Test calling the subfunctions
    """
    def test_get_image_crop_box(self):
        #assert get_wiki_images.get_image_crop_box(temp_image_path) == {
        #    "x": 50,
        #    "y": 75,
        #    "width": 300,
        #    "height": 300,
        #}
        pass


class TestAPI:
    apis = RemoteAPIs(mock_qid=-1234)

    def check_downloaded_wiki_image(self, qid, crop=None):
        img_dir = os.path.join(self.tmp_dir, str(src_flags["wiki"]), str(qid)[-3:])
        if os.path.exists(os.path.join(img_dir, f"{qid}.jpg")):
            uncropped = os.path.join(img_dir, f"{qid}_uncropped.jpg")
            assert os.path.exists(uncropped)
            w, h = Image.open(uncropped).size
            assert (w, h) == Image.open(self.apis.temp_image_path).size
            cropped = os.path.join(img_dir, f"{qid}.jpg")
            assert os.path.exists(cropped)
            assert Image.open(cropped).size == (300, 300)
            cropinfo = os.path.join(img_dir, f"{qid}_cropinfo.txt")
            assert os.path.exists(cropinfo)
            if crop is None:
                # No Azure, so should have taken the default size
                with open(cropinfo) as f:
                    s = f.read()
                    if h > w:
                        assert s.startswith(f"0,")
                        assert s.endswith(f",{w},{w}")
                    else:    
                        assert s.endswith(f",0,{h},{h}")
            return True
        return False

    @apis.mock_patch_all_web_request_methods
    def verify_process_leaf(self, image, rating, *args):
        db = self.db
        ott = self.ott
        ph = placeholder(db)
        qid = self.apis.mock_qid
        crp = None
        img_sql = "SELECT src_id, rating FROM images_by_ott WHERE ott={0};"
        vn_sql = "SELECT vernacular FROM vernacular_by_ott WHERE ott={0};"

        get_wiki_images.process_leaf(db, ott, output_dir=self.tmp_dir, skip_images=True)
        # Quick check on vernaculars - should work even with the real wiki API
        names = {r[0] for r in self.db.executesql(vn_sql.format(ph), (self.ott,))}
        assert "Lion" in names

        # Images skipped, so should have no row
        rows = self.db.executesql(img_sql.format(ph), (self.ott,))
        assert len(rows) == 0
        assert not self.check_downloaded_wiki_image(qid)

        # Now get images
        get_wiki_images.process_leaf(
            db, ott, rating=rating, output_dir=self.tmp_dir, skip_images=False, crop=crp
        )
        assert self.check_downloaded_wiki_image(qid, crp)
        rows = self.db.executesql(img_sql.format(ph), (self.ott,))
        assert len(rows) == 1
        assert rows[0] == (qid, 40123)

    def test_process_default_leaf(self, db, keep_rows, tmp_path):
        self.ott = "-551"
        self.db = db
        self.tmp_dir = tmp_path
        qid = self.apis.mock_qid
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
        # TODO!
        pass


class TestCLI:
    apis = RemoteAPIs(mock_qid=-4312)

    def test_get_leaf_default_image(self, tmp_path, db, appconfig, keep_rows, real_apis):
        self.db = db
        self.appconfig = appconfig
        self.ott = "-771"
        self.tmp_path = tmp_path
        self.real_apis = real_apis
        delete_rows(db, self.ott)
        self.verify_image_behavior(None, None)
        if not keep_rows:
            delete_rows(db, self.ott)

    def test_get_leaf_bespoke_image(self, tmp_path, db, appconfig, keep_rows, real_apis):
        self.db = db
        self.appconfig = appconfig
        self.ott = "-772"
        self.tmp_path = tmp_path
        self.real_apis = real_apis
        delete_rows(db, self.ott)
        self.verify_image_behavior("SecondLionImage.jpg", 42000)
        if not keep_rows:
            delete_rows(db, self.ott)

    def verify_image_behavior(self, image, rating, *args):
        assert int(self.ott) < 0
        ph = placeholder(self.db)
        qid = self.apis.true_qid if self.real_apis else self.apis.mock_qid
        # Insert a leaf to set up the mapping between the ott and the wikidata id
        self.db.executesql(
            "INSERT INTO ordered_leaves (parent, real_parent, name, ott, wikidata) "
            "VALUES (0, 0, {0}, {0}, {0});".format(ph),
            ("Panthera leo", self.ott, qid),
        )
        # Note that the image src should be onezoom_bespoke if a bespoke image is used
        src = src_flags["onezoom_bespoke"] if image else src_flags["wiki"]

        # Insert a dummy image to test that it gets deleted in the wiki case, and kept in the bespoke case
        src_id = get_next_src_id_for_src(self.db, src)
        self.db.executesql(
            "INSERT INTO images_by_ott "
            "(ott, src, src_id, url, rating, best_any, best_verified, best_pd, overall_best_any, "
            "overall_best_verified, overall_best_pd) "
            "VALUES ({0}, {0}, {0}, {0}, 1234, 1, 1, 1, 1, 1, 1);".format(ph),
            (self.ott, src, src_id, "http://example.com/dummy.jpg"),
        )
        self.db.commit()
        # Call the method that we want to test
        params = get_command_arguments("leaf", [self.ott], image, rating, self.tmp_path, self.appconfig)

        if self.real_apis:
            get_wiki_images.process_args(params)
        else:
            self.mock_process_args(params, *args)

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
            "SELECT ott, vernacular, lang_primary, lang_full, preferred FROM vernacular_by_ott "
            f"WHERE ott={ph} ORDER BY lang_full, preferred DESC",
            (self.ott, ),
        )
        count_preferred = {}
        for r in rows:
            full_lang = r[3]
            assert full_lang.startswith(r[2])
            if full_lang not in count_preferred:
                count_preferred[full_lang] = 0
            count_preferred[full_lang] += int(r[4])
        assert all([v == 1 for v in count_preferred.values()])

        if not self.real_apis:
            # Check the expected values
            names = tuple((r[1], r[2]) for r in rows)
            assert names == self.apis.expected_mock_vn_order

    @apis.mock_patch_all_web_request_methods
    def mock_process_args(self, params, *args):
        get_wiki_images.process_args(params)




