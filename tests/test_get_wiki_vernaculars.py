import logging
from types import SimpleNamespace

import pytest

from oz_tree_build.vernaculars import get_wiki_vernaculars
from oz_tree_build.utilities.db_helper import placeholder

from .wiki_test_helpers import (
    RemoteAPIs,
    delete_rows,
)


class TestFunctions:
    def test_get_vernaculars_by_language_from_json_item(self):
        apis = RemoteAPIs(mock_qid=-9999)
        wikidata = apis.wikidata_response(
            image_data=[],
            vernacular_data=[
                {"name": "Löwe", "language": "de", "rank": "normal"},
                {"name": "Lion", "language": "en", "rank": "normal"},
                {"name": "Lion", "language": "fr", "rank": "preferred"},
                {"name": "African Lion", "language": "en", "rank": "preferred"},
                {"name": "Lion d'Afrique", "language": "fr", "rank": "preferred"},
            ],
        )["response"]["entities"]["Q-9999"]
        vernaculars = get_wiki_vernaculars.get_vernaculars_by_language_from_json_item(wikidata)
        assert vernaculars["de"] == [{"name": "Löwe", "preferred": 1}]
        assert vernaculars["en"] == [
            {"name": "African Lion", "preferred": 1},
            {"name": "Lion", "preferred": 0},
        ]
        assert vernaculars["fr"] == [
            {"name": "Lion", "preferred": 1},
            {"name": "Lion d'Afrique", "preferred": 0},
        ]


class TestAPI:
    apis = RemoteAPIs(mock_qid=-1234)

    def setup_lookups(self, db, qid, keep_rows, ott=None, repeat_rows=1, name="Panthera leo"):
        self.db = db
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

    def vernacular_rows_in_db(self, ott=None):
        sql = (
            "SELECT vernacular, lang_primary, lang_full, preferred "
            f"FROM vernacular_by_ott WHERE ott={placeholder(self.db)} "
            "ORDER BY lang_full, preferred DESC"
        )
        if ott is None:
            ott = self.ott
        return self.db.executesql(sql, (ott,))

    def vernaculars_in_db(self, ott=None):
        return {r[0] for r in self.vernacular_rows_in_db(ott)}

    @apis.mock_patch_all_web_request_methods
    def verify_process_leaf(self, *args):
        get_wiki_vernaculars.process_leaf(self.db, self.ott or self.taxon_name)

    @pytest.mark.parametrize("use_ott", [True, False])
    def test_process_default_leaf(self, db, use_ott, keep_rows, caplog):
        ott = "-651"
        sp_name = "Thisisnota speciesname"
        if use_ott:
            self.ott = ott
        else:
            self.ott = None
            self.taxon_name = sp_name
        self.setup_lookups(db, self.apis.mock_qid, keep_rows, ott=ott, name=sp_name)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf()
        assert caplog.text == ""
        assert "Lion" in self.vernaculars_in_db(ott)
        rows = self.vernacular_rows_in_db(ott)
        names = tuple((r[0], r[1]) for r in rows)
        assert names == self.apis.expected_mock_vn_order
        count_preferred = {}
        for r in rows:
            full_lang = r[2]
            assert full_lang.startswith(r[1])
            count_preferred.setdefault(full_lang, 0)
            count_preferred[full_lang] += int(r[3])
        assert all(v == 1 for v in count_preferred.values())
        self.teardown_lookups(ott=ott)

    def test_multiple_ott(self, db, keep_rows, caplog):
        self.ott = "-652"
        self.setup_lookups(db, self.apis.mock_qid, keep_rows, repeat_rows=2)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf()
        assert "Multiple" in caplog.text
        assert len(self.vernaculars_in_db()) == 0
        self.teardown_lookups()

    def test_no_ott(self, db, keep_rows, caplog):
        ordered_leaf_ott = -1111112
        self.ott = "-653"
        self.setup_lookups(db, self.apis.mock_qid, keep_rows, ott=ordered_leaf_ott)
        with caplog.at_level(logging.WARNING):
            self.verify_process_leaf()
        assert "not found in ordered_leaves table" in caplog.text
        assert len(self.vernaculars_in_db()) == 0
        self.teardown_lookups(ott=ordered_leaf_ott)


class TestCLI:
    apis = RemoteAPIs(mock_qid=-4312)

    def test_get_leaf_default_vernaculars(self, db, conf_file, keep_rows, real_apis):
        self.db = db
        self.conf_file = conf_file
        self.ott = "-871"
        self.real_apis = real_apis
        delete_rows(db, self.ott)
        self.verify_vernacular_behavior()
        if not keep_rows:
            delete_rows(db, self.ott)

    def verify_vernacular_behavior(self, *args):
        assert int(self.ott) < 0
        s = placeholder(self.db)
        qid = self.apis.true_qid if self.real_apis else self.apis.mock_qid
        self.db.executesql(
            "INSERT INTO ordered_leaves (parent, real_parent, name, ott, wikidata) " f"VALUES (0, 0, {s}, {s}, {s});",
            ("Panthera leo", self.ott, qid),
        )
        self.db.commit()
        params = SimpleNamespace(
            subcommand="leaf",
            ott_or_taxa=[self.ott],
            conf_file=self.conf_file,
            taxa_data_file=None,
            verbosity=0,
            quiet=0,
        )
        if self.real_apis:
            get_wiki_vernaculars.process_args(params)
        else:
            self.mock_process_args(params, *args)

        rows = self.db.executesql(
            "SELECT ott, vernacular, lang_primary, lang_full, preferred "
            f"FROM vernacular_by_ott WHERE ott={s} ORDER BY lang_full, preferred DESC",
            (self.ott,),
        )
        count_preferred = {}
        for r in rows:
            full_lang = r[3]
            assert full_lang.startswith(r[2])
            count_preferred.setdefault(full_lang, 0)
            count_preferred[full_lang] += int(r[4])
        assert all(v == 1 for v in count_preferred.values())

        if not self.real_apis:
            names = tuple((r[1], r[2]) for r in rows)
            assert names == self.apis.expected_mock_vn_order

    @apis.mock_patch_all_web_request_methods
    def mock_process_args(self, params, *args):
        get_wiki_vernaculars.process_args(params)
