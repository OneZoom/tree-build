import logging
import os
import shutil
import urllib.request
from types import SimpleNamespace
from unittest import mock

import pytest
from PIL import Image

from oz_tree_build._OZglobals import src_flags
from oz_tree_build.images_and_vernaculars import get_wiki_images
from oz_tree_build.utilities.db_helper import (
    delete_all_by_ott,
    get_next_src_id_for_src,
    placeholder,
)

# These need to be real images to make the --real-apis mode work
first_lion_image_name = "Okonjima_Lioness.jpg"
second_lion_image_name = "Lioness_12.jpg"


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

        # Download an arbitrary test image in the tmp folder to use in the tests
        self.temp_image_path = "/tmp/mocked_urlretrieve_image.jpg"
        if not os.path.exists(self.temp_image_path):
            image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Lion_waiting_in_Namibia.jpg/500px-Lion_waiting_in_Namibia.jpg"
            urllib.request.urlretrieve(image_url, self.temp_image_path)
        with open(self.temp_image_path, "rb") as f:
            self.temp_image_content = f.read()

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
        self.add_mocked_request(**self.wikimedia_file_response(second_lion_image_name))
        self.add_mocked_request(**self.wikimedia_response("NoArtist.jpg", artist=None))
        self.add_mocked_request(**self.wikimedia_file_response("NoArtist.jpg"))
        self.add_mocked_request(**self.wikimedia_response("PublicDomain.jpg", licence="pd-NOOA"))
        self.add_mocked_request(**self.wikimedia_file_response("PublicDomain.jpg"))
        self.add_mocked_request(**self.wikimedia_response("CC-BY3.jpg", licence="cc-by-3.0"))
        self.add_mocked_request(**self.wikimedia_file_response("CC-BY3.jpg"))
        self.add_mocked_request(**self.wikimedia_response("Flickr.jpg", licence="flickr_commons"))
        self.add_mocked_request(**self.wikimedia_file_response("Flickr.jpg"))
        self.add_mocked_request(**self.wikimedia_response("BadLicence.jpg", "GPL"))
        self.add_mocked_request(
            # This should not be called: if license is bad => don't download
            **self.wikimedia_file_response("BadLicence.jpg", "xxx")
        )

    # Mock the requests.get function
    def mocked_requests_get(self, *args, **kwargs):
        if args[0] in self.mocked_requests:
            content = self.temp_image_content if args[0].endswith(".jpg") else None
            return MockResponse(200, self.mocked_requests[args[0]], content)
        return MockResponse(404)

    def mocked_urlretrieve(self, *args, **kwargs):
        # Instead of actually downloading, just copy the test image to the destination
        if not args[0].startswith("http"):
            raise ValueError("Only HTTP URLs are supported in these tests")
        shutil.copyfile(self.temp_image_path, args[1])

    # Mock the Azure Vision API smart crop response
    def mocked_analyze_from_url(self, *args, **kwargs):
        return SimpleNamespace(
            smart_crops=SimpleNamespace(
                list=[SimpleNamespace(bounding_box=SimpleNamespace(x=50, y=75, width=300, height=300))]
            )
        )

    def wikimedia_file_response(self, image_name, url=None):
        if url is None:
            url = "https://upload.wikimedia.org/wikipedia/commons/not/a/real/image.jpg"
        return {
            "url": f"https://api.wikimedia.org/core/v1/commons/file/{image_name}",
            "response": {
                "preferred": {"url": url}  # means preferred image *size* not preferred image
            },
        }

    def wikimedia_response(self, image_name, licence="cc0", artist="John Doe"):
        # NB use british spelling of licence to avoid shadowing python builtin
        url = (
            "https://api.wikimedia.org/w/api.php"
            f"?action=query&titles=File%3a{image_name}&format=json&prop=imageinfo"
            "&iiprop=extmetadata&iiextmetadatafilter=License|LicenseUrl|Artist"
        )
        response = {
            "query": {
                "pages": {
                    "-1": {
                        "title": "File:Blah.jpg",
                        "imageinfo": [{"extmetadata": {}}],
                    }
                }
            }
        }
        extmetadata = response["query"]["pages"]["-1"]["imageinfo"][0]["extmetadata"]
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


def get_command_arguments(subcommand, ott_or_taxa, image, rating, output_dir, conf_file):
    return SimpleNamespace(
        subcommand=subcommand,
        ott_or_taxa=ott_or_taxa,
        image=image,
        rating=rating,
        skip_images=None,
        output_dir=output_dir,
        conf_file=conf_file,
        taxa_data_file=None,
    )


def default_rating(image=None):
    if image is None:
        return get_wiki_images.default_wiki_image_rating
    return get_wiki_images.bespoke_wiki_image_rating


class TestFunctions:
    """
    Test calling the subfunctions
    """

    def test_get_image_crop_box(self):
        # assert get_wiki_images.get_image_crop_box(temp_image_path) == {
        #    "x": 50,
        #    "y": 75,
        #    "width": 300,
        #    "height": 300,
        # }
        pass


class TestAPI:
    apis = RemoteAPIs(mock_qid=-1234)

    def setup_lookups(self, db, qid, tmp_path, keep_rows, ott=None, repeat_rows=1, name="Panthera leo"):
        self.db = db
        self.tmp_dir = tmp_path
        self.keep_rows = keep_rows
        self.qid = qid
        if ott is None:
            ott = self.ott
        delete_rows(db, ott)
        for _ in range(repeat_rows):
            db.executesql(
                "INSERT INTO ordered_leaves (parent, real_parent, name, ott, wikidata) "
                "VALUES (0, 0, {0}, {0}, {0});".format(placeholder(db)),
                (name, ott, qid),
            )

    def teardown_lookups(self, ott=None):
        if ott is None:
            ott = self.ott
        if not self.keep_rows:
            delete_rows(self.db, ott)

    def check_downloaded_wiki_image(self, qid, cropper=None, is_wikidata=True):
        src_dir = str(src_flags["wiki"]) if is_wikidata else str(src_flags["onezoom_bespoke"])
        img_dir = os.path.join(self.tmp_dir, src_dir, str(qid)[-3:])
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
            if cropper is None:
                # No Azure, so should have taken the default size
                with open(cropinfo) as f:
                    s = f.read()
                    if h > w:
                        assert s.startswith("0,")
                        assert s.endswith(f",{w},{w}")
                    else:
                        assert s.endswith(f",0,{h},{h}")
            return True
        return False

    def vernaculars_in_db(self, ott=None):
        sql = f"SELECT vernacular FROM vernacular_by_ott WHERE ott={placeholder(self.db)};"
        if ott is None:
            ott = self.ott
        return {r[0] for r in self.db.executesql(sql, (ott,))}

    def image_rows_in_db(self, ott=None):
        sql = "SELECT src_id, rating, rights, licence FROM images_by_ott " f"WHERE ott={placeholder(self.db)};"
        if ott is None:
            ott = self.ott
        return self.db.executesql(sql, (ott,))

    @apis.mock_patch_all_web_request_methods
    def verify_process_leaf(self, image=None, rating=None, skip_images=None, cropper=None, *args):
        get_wiki_images.process_leaf(
            self.db,
            self.ott or self.taxon_name,
            image,
            rating=rating,
            output_dir=self.tmp_dir,
            skip_images=skip_images,
            cropper=cropper,
        )

    @pytest.mark.parametrize("use_ott", [True, False])
    def test_process_default_leaf(self, db, use_ott, tmp_path, keep_rows, caplog):
        ott = "-551"
        sp_name = "Thisisnota speciesname"
        if use_ott:
            self.ott = ott
        else:
            self.ott = None
            self.taxon_name = sp_name
        cropper = None
        image = None  # The name of the image to get or None to use the default WD image
        rating = 40123
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows, ott=ott, name=sp_name)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(image, rating, False, cropper)
        assert caplog.text == ""
        assert self.check_downloaded_wiki_image(self.qid, cropper, image is None)
        assert "Lion" in self.vernaculars_in_db(ott)
        rows = self.image_rows_in_db(ott)
        assert len(rows) == 1
        assert rows[0] == (
            self.qid,
            rating or default_rating(image),
            "John Doe",
            "Released into the public domain",
        )
        self.teardown_lookups(ott=ott)

    def test_process_default_leaf_skip_images(self, db, tmp_path, keep_rows):
        self.ott = "-552"
        cropper = None
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows)
        self.verify_process_leaf(None, None, True, cropper)
        # Images skipped, so should have no row
        assert "Lion" in self.vernaculars_in_db()
        assert not self.check_downloaded_wiki_image(self.qid, cropper)
        assert len(self.image_rows_in_db()) == 0
        self.teardown_lookups()

    def test_alt_cc_license(self, db, tmp_path, keep_rows, caplog):
        self.ott = "-553"
        cropper = None
        image = "CC-BY3.jpg"
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows)
        # self.tmp_dir = "../OZtree/static/FinalOutputs/img/"
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(image, None, False, cropper)
        rows = self.image_rows_in_db()
        assert len(rows) == 1
        assert rows[0][1:] == (
            default_rating(image),
            "© John Doe",
            f"cc-by-3.0 ({self.apis.license_urls['cc-by-3.0']})",
        )
        assert self.check_downloaded_wiki_image(rows[0][0], cropper, image is None)
        self.teardown_lookups()

    def test_pd_license(self, db, tmp_path, keep_rows, caplog):
        self.ott = "-554"
        cropper = None
        image = "PublicDomain.jpg"
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(image, None, False, cropper)
        rows = self.image_rows_in_db()
        assert len(rows) == 1
        assert rows[0][1:] == (
            default_rating(image),
            "John Doe",
            "Marked as being in the public domain",
        )
        assert self.check_downloaded_wiki_image(rows[0][0], cropper, image is None)
        self.teardown_lookups()

    def test_flickr_license(self, db, tmp_path, keep_rows, caplog):
        self.ott = "-555"
        cropper = None
        rating = 44444
        image = "Flickr.jpg"
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(image, rating, False, cropper)
        assert "Lion" in self.vernaculars_in_db()
        rows = self.image_rows_in_db()
        assert len(rows) == 1
        assert rows[0][1:] == (
            rating or default_rating(image),
            "John Doe",
            "Marked on Flickr commons as being in the public domain",
        )
        assert self.check_downloaded_wiki_image(rows[0][0], cropper, image is None)
        self.teardown_lookups()

    def test_no_artist(self, db, tmp_path, keep_rows, caplog):
        self.ott = "-556"
        cropper = None
        rating = 40123
        image = "NoArtist.jpg"
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows)
        # self.tmp_dir = "../OZtree/static/FinalOutputs/img/"
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(image, rating, False, cropper)
        assert "Artist not found" in caplog.text
        assert "Lion" in self.vernaculars_in_db()
        rows = self.image_rows_in_db()
        assert len(rows) == 1
        assert rows[0][1:] == (
            rating or default_rating(image),
            "Unknown artist",
            "Released into the public domain",
        )
        assert self.check_downloaded_wiki_image(rows[0][0], cropper, image is None)
        self.teardown_lookups()

    def test_bad_licence(self, db, tmp_path, keep_rows, caplog):
        self.ott = "-557"
        cropper = None
        image = "BadLicence.jpg"
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(image, None, False, cropper)
        assert "Unacceptable license" in caplog.text
        assert "Lion" in self.vernaculars_in_db()
        assert not self.check_downloaded_wiki_image(self.qid, cropper, image is None)
        assert len(self.image_rows_in_db()) == 0
        self.teardown_lookups()

    def test_multiple_ott(self, db, tmp_path, keep_rows, caplog):
        self.ott = "-558"
        cropper = None
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows, repeat_rows=2)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(None, None, False, cropper)
        assert "Multiple" in caplog.text
        assert len(self.vernaculars_in_db()) == 0
        assert not self.check_downloaded_wiki_image(self.qid, cropper)
        assert len(self.image_rows_in_db()) == 0
        self.teardown_lookups()

    def test_no_ott(self, db, tmp_path, keep_rows, caplog):
        ordered_leaf_ott = -1111111
        self.ott = "-559"
        cropper = None
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows, ott=ordered_leaf_ott)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(None, None, False, cropper)
        assert "not found in ordered_leaves table" in caplog.text
        assert len(self.vernaculars_in_db()) == 0
        assert not self.check_downloaded_wiki_image(self.qid, cropper)
        assert len(self.image_rows_in_db()) == 0
        self.teardown_lookups(ott=ordered_leaf_ott)

    @pytest.mark.skip(reason="https://github.com/OneZoom/tree-build/issues/78")
    def test_existing_image_rating_kept(self, db, keep_rows, tmp_path):
        self.ott = "-560"
        cropper = None
        self.setup(db, self.apis.mock_qid, tmp_path, keep_rows)
        self.verify_process_leaf(None, None, None, cropper)
        rows = self.image_rows_in_db()
        assert rows[0][1] == default_rating()
        self.verify_process_leaf(None, 44444, None, cropper)
        assert rows[0][1] == 44444
        self.verify_process_leaf(None, None, None, cropper)
        assert rows[0][1] == 44444
        self.verify_process_leaf(None, 40123)
        assert rows[0][1] == 40123
        self.teardown()

    @pytest.mark.skip_real_apis()
    def test_process_clade(self):
        # TODO! We need to creata a fake filtered wikidata JSON dump with a 2 taxa
        # with different (negative) qIDs.
        pass


class TestCLI:
    apis = RemoteAPIs(mock_qid=-4312)

    def test_get_leaf_default_image(self, tmp_path, db, conf_file, keep_rows, real_apis):
        self.db = db
        self.conf_file = conf_file
        self.ott = "-771"
        self.tmp_path = tmp_path
        self.real_apis = real_apis
        delete_rows(db, self.ott)
        self.verify_image_behavior(None, None)
        if not keep_rows:
            delete_rows(db, self.ott)

    def test_get_leaf_bespoke_image(self, tmp_path, db, conf_file, keep_rows, real_apis):
        self.db = db
        self.conf_file = conf_file
        self.ott = "-772"
        self.tmp_path = tmp_path
        self.real_apis = real_apis
        delete_rows(db, self.ott)
        self.verify_image_behavior(second_lion_image_name, 42000)
        if not keep_rows:
            delete_rows(db, self.ott)

    def verify_image_behavior(self, image, rating, *args):
        assert int(self.ott) < 0
        s = placeholder(self.db)
        qid = self.apis.true_qid if self.real_apis else self.apis.mock_qid
        # Insert a leaf to set up the mapping between the ott and the wikidata id
        self.db.executesql(
            "INSERT INTO ordered_leaves (parent, real_parent, name, ott, wikidata) " f"VALUES (0, 0, {s}, {s}, {s});",
            ("Panthera leo", self.ott, qid),
        )
        # Note that the image src should be onezoom_bespoke if a bespoke image is used
        src = src_flags["onezoom_bespoke"] if image else src_flags["wiki"]

        # Insert a dummy image to test that it gets deleted in the wiki case and
        # kept in the bespoke case
        src_id = get_next_src_id_for_src(self.db, src)
        self.db.executesql(
            "INSERT INTO images_by_ott "
            "(ott, src, src_id, url, rating, licence, best_any, best_verified, best_pd, "
            "overall_best_any, overall_best_verified, overall_best_pd) "
            f"VALUES ({s}, {s}, {s}, {s}, 1234, {s}, 1, 1, 1, 1, 1, 1);",
            (self.ott, src, src_id, "http://example.com/dummy.jpg", "cc0"),
        )
        self.db.commit()
        # Call the method that we want to test
        params = get_command_arguments("leaf", [self.ott], image, rating, self.tmp_path, self.conf_file)

        if self.real_apis:
            get_wiki_images.process_args(params)
        else:
            self.mock_process_args(params, *args)

        rows = self.db.executesql(
            "SELECT ott, src, src_id, rating, overall_best_any FROM images_by_ott " f"WHERE ott={s} ORDER BY id desc;",
            (self.ott,),
        )
        # There should only be one image in the database in wiki mode
        # (since we delete first), and two in bespoke mode
        assert len(rows) == 1 if src == src_flags["wiki"] else 2
        # Check the image details: src_id should be one more than the test row
        # in the bespoke case, and the qid in the wiki case
        assert rows[0] == (
            int(self.ott),
            src,
            src_id + 1 if src == src_flags["onezoom_bespoke"] else int(qid),
            rating if rating else default_rating(image),
            1,
        )
        # In the bespoke case, process_image_bits at the end of get_wiki_images should
        # set the overall_best_any bit to 0 for the dummy image (we set it to 1 above)
        if src == src_flags["onezoom_bespoke"]:
            assert rows[1][4] == 0
        # Check the vernacular names
        rows = self.db.executesql(
            "SELECT ott, vernacular, lang_primary, lang_full, preferred "
            f"FROM vernacular_by_ott WHERE ott={s} ORDER BY lang_full, preferred DESC",
            (self.ott,),
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
