import logging
import os
from types import SimpleNamespace

import pytest
from PIL import Image

from oz_tree_build._OZglobals import src_flags
from oz_tree_build.images import get_wiki_images
from oz_tree_build.utilities.db_helper import get_next_src_id_for_src, placeholder

from .wiki_test_helpers import (
    RemoteAPIs,
    default_rating,
    delete_rows,
    second_lion_image_name,
)


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
            assert (w, h) == (500, 500)  # Dimensions of TINY_JPEG
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

    def image_rows_in_db(self, ott=None):
        sql = "SELECT src_id, rating, rights, licence FROM images_by_ott " f"WHERE ott={placeholder(self.db)};"
        if ott is None:
            ott = self.ott
        return self.db.executesql(sql, (ott,))

    @apis.mock_patch_all_web_request_methods
    def verify_process_leaf(self, image=None, rating=None, cropper=None, *args):
        get_wiki_images.process_leaf(
            self.db,
            self.ott or self.taxon_name,
            image,
            rating=rating,
            output_dir=self.tmp_dir,
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
            self.verify_process_leaf(image, rating, cropper)
        assert caplog.text == ""
        assert self.check_downloaded_wiki_image(self.qid, cropper, image is None)
        rows = self.image_rows_in_db(ott)
        assert len(rows) == 1
        assert rows[0] == (
            self.qid,
            rating or default_rating(image),
            "John Doe",
            "Released into the public domain",
        )
        self.teardown_lookups(ott=ott)

    def test_alt_cc_license(self, db, tmp_path, keep_rows, caplog):
        self.ott = "-553"
        cropper = None
        image = "CC-BY3.jpg"
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows)
        # self.tmp_dir = "../OZtree/static/FinalOutputs/img/"
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(image, None, cropper)
        response = self.apis.mocked_requests[self.apis.wikimedia_response(image)["url"]]
        # Check response is lowercase
        assert response["query"]["pages"]["12345"]["imageinfo"][0]["extmetadata"]["License"]["value"].startswith(
            "cc-by"
        )
        rows = self.image_rows_in_db()
        assert len(rows) == 1
        assert rows[0][1:] == (
            default_rating(image),
            "© John Doe",
            # License should be capitalised
            f"CC-BY-3.0 ({self.apis.license_urls['cc-by-3.0']})",
        )
        assert self.check_downloaded_wiki_image(rows[0][0], cropper, image is None)
        self.teardown_lookups()

    def test_pd_license(self, db, tmp_path, keep_rows, caplog):
        self.ott = "-554"
        cropper = None
        image = "PublicDomain.jpg"
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(image, None, cropper)
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
            self.verify_process_leaf(image, rating, cropper)
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
            self.verify_process_leaf(image, rating, cropper)
        assert "Artist not found" in caplog.text
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
            self.verify_process_leaf(image, None, cropper)
        assert "Unacceptable license" in caplog.text
        assert not self.check_downloaded_wiki_image(self.qid, cropper, image is None)
        assert len(self.image_rows_in_db()) == 0
        self.teardown_lookups()

    def test_multiple_ott(self, db, tmp_path, keep_rows, caplog):
        self.ott = "-558"
        cropper = None
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows, repeat_rows=2)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(None, None, cropper)
        assert "Multiple" in caplog.text
        assert not self.check_downloaded_wiki_image(self.qid, cropper)
        assert len(self.image_rows_in_db()) == 0
        self.teardown_lookups()

    def test_no_ott(self, db, tmp_path, keep_rows, caplog):
        ordered_leaf_ott = -1111111
        self.ott = "-559"
        cropper = None
        self.setup_lookups(db, self.apis.mock_qid, tmp_path, keep_rows, ott=ordered_leaf_ott)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf(None, None, cropper)
        assert "not found in ordered_leaves table" in caplog.text
        assert not self.check_downloaded_wiki_image(self.qid, cropper)
        assert len(self.image_rows_in_db()) == 0
        self.teardown_lookups(ott=ordered_leaf_ott)

    @pytest.mark.skip(reason="https://github.com/OneZoom/tree-build/issues/78")
    def test_existing_image_rating_kept(self, db, keep_rows, tmp_path):
        self.ott = "-560"
        cropper = None
        self.setup(db, self.apis.mock_qid, tmp_path, keep_rows)
        self.verify_process_leaf(None, None, cropper)
        rows = self.image_rows_in_db()
        assert rows[0][1] == default_rating()
        self.verify_process_leaf(None, 44444, cropper)
        assert rows[0][1] == 44444
        self.verify_process_leaf(None, None, cropper)
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
        params = SimpleNamespace(
            subcommand="leaf",
            ott_or_taxa=[self.ott],
            image=image,
            rating=rating,
            output_dir=self.tmp_path,
            conf_file=self.conf_file,
            taxa_data_file=None,
            no_azure_crop=True,
        )

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

    @apis.mock_patch_all_web_request_methods
    def mock_process_args(self, params, *args):
        get_wiki_images.process_args(params)
