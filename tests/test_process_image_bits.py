import datetime
import types

import pytest

from oz_tree_build.images_and_vernaculars import process_image_bits
from oz_tree_build.utilities.db_helper import (
    connect_to_database,
    delete_all_by_ott,
    placeholder,
)


class TestDBHelper:
    def test_connect_to_database(self, conf_file):
        db = connect_to_database(conf_file=conf_file)
        assert tuple(db.executesql("SELECT 1;")) == ((1,),)
        # The following should pass without error if the tables exist
        db.executesql("SELECT id from images_by_ott LIMIT 1")
        db.executesql("SELECT id from vernacular_by_ott LIMIT 1")
        db.executesql("SELECT id from ordered_leaves LIMIT 1")
        db.close()


class BaseDB:
    get_sql = (
        "SELECT best_any, overall_best_any, best_verified, overall_best_verified, "
        "best_pd, overall_best_pd FROM images_by_ott WHERE ott={0} ORDER BY id;"
    )
    set_sql = (
        "INSERT INTO images_by_ott "
        "(ott,src,src_id,url,rating,rights,licence,best_any,overall_best_any,"
        "best_verified,overall_best_verified,best_pd,overall_best_pd,updated) "
        "VALUES ({0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0});"
    )


class TestAPI(BaseDB):
    """
    Test calling the .resolve() function directly.
    """

    def test_empty(self, db):
        ott = -111
        # Delete the test rows before starting the test.
        delete_all_by_ott(db, "images_by_ott", ott)
        process_image_bits.resolve(db, ott)

    def test_single(self, db, keep_rows):
        ott = -112
        ph = placeholder(db)
        # Delete the test rows before starting the test.
        # We don't delete them at the end, because we want to see the results manually.
        delete_all_by_ott(db, "images_by_ott", ott)
        test_row = [ott, 20, -3, "foo.jpg", 24000, "Unknown", "cc0 (...)", 0, 0, 0, 0, 0, 0]
        sql = self.set_sql.format(ph)
        db.executesql(sql, [*test_row, datetime.datetime.now()])
        made_changes = process_image_bits.resolve(db, ott)
        assert made_changes
        sql = self.get_sql.format(ph)
        rows = db.executesql(sql, (ott,))
        assert len(rows) == 1
        assert tuple(rows[0]) == (1, 1, 1, 1, 1, 1)
        if not keep_rows:
            delete_all_by_ott(db, "images_by_ott", ott)
            rows = db.executesql(sql, (ott,))
            assert len(rows) == 0

    def test_verified_bit_kept_for_old(self, db, keep_rows):
        # Images from potentially unverified sources (e.g. src 99) may have their
        # best_verified bit set to 1: we should pick the one of these with
        # the highest rating any only set that image to best_verified for that
        # source_id. Note that this means there is a bug whereby we loose the
        # verified status of all other images for that ott + src
        pass
        ott = -112
        ph = placeholder(db)
        r = []
        # Delete the test rows before starting the test.
        # We don't delete them at the end, because we want to see the results manually.
        delete_all_by_ott(db, "images_by_ott", ott)
        r.append([ott, 99, -91, "A.jpg", 24000, "Unknown", "cc0 (...)", 0, 0, 0, 0, 0, 0])
        r.append([ott, 99, -92, "B.jpg", 44000, "Unknown", "public domain", 0, 0, 0, 0, 0, 0])
        r.append([ott, 99, -93, "C.jpg", 24000, "Unknown", "cc-by (...)", 0, 0, 1, 0, 0, 0])
        r.append([ott, 99, -94, "D.jpg", 36000, "Unknown", "cc-by (...)", 0, 0, 1, 0, 0, 0])
        r.append([ott, 99, -94, "E.jpg", 20000, "Unknown", "cc-by (...)", 0, 0, 1, 0, 0, 0])
        r.append([ott, 20, -95, "F.jpg", 35000, "Unknown", "cc0 (...)", 0, 0, 0, 0, 0, 0])
        sql = self.set_sql.format(ph)
        for row in r:
            db.executesql(sql, [*row, datetime.datetime.now()])
        made_changes = process_image_bits.resolve(db, ott)
        assert made_changes
        sql = self.get_sql.format(ph)
        rows = db.executesql(sql, (ott,))
        print(rows)
        assert tuple(rows[0]) == (0, 0, 0, 0, 0, 0)
        assert tuple(rows[1]) == (1, 1, 0, 0, 1, 1)
        assert tuple(rows[2]) == (0, 0, 0, 0, 0, 0)
        assert tuple(rows[3]) == (0, 0, 1, 1, 0, 0)  # best verified & best overall verified
        assert tuple(rows[4]) == (0, 0, 0, 0, 0, 0)
        assert tuple(rows[5]) == (1, 0, 1, 0, 1, 0)
        if not keep_rows:
            delete_all_by_ott(db, "images_by_ott", ott)
            rows = db.executesql(sql, (ott,))
            assert len(rows) == 0


class TestCLI(BaseDB):
    """
    Test calling process_args() as would be done using the command-line.
    """

    def check_database_content(self, args, expected_results, db):
        # Query the database and check the results
        rows = db.executesql(self.get_sql.format(placeholder(db)), (args.ott,))
        for i, row in enumerate(rows):
            assert row == expected_results[i]

    @pytest.mark.parametrize("init_value", [0, 1])
    def test_process_image_bits(self, db, conf_file, keep_rows, init_value):
        args = types.SimpleNamespace(ott=-777, conf_file=conf_file)
        # Delete the test rows before starting the test.
        # We don't delete them at the end, because we want to see the results manually.

        delete_all_by_ott(db, "images_by_ott", args.ott)

        v = init_value
        name = "foo.jpg"
        rights = "Unknown"
        # fmt: off
        test_rows = [
            [args.ott, 20, -1, name, 24000, rights, "cc0 (...)", v, v, v, v, v, v],
            [args.ott, 20, -2, name, 29000, rights, "pd (...)", v, v, v, v, v, v],
            [args.ott, 20, -3, name, 33000, rights, "cc0 (...)", v, v, v, v, v, v],
            [args.ott, 20, -4, name, 25000, rights, "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 20, -4, name, 30000, rights, "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 20, -5, name, 35000, rights, "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 2, -6, name, 28000, rights, "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 21, -6, name, 23000, rights, "cc0 (...)", v, v, v, v, v, v],
            [args.ott, 21, -5, name, 29000, rights, "pd (...)", v, v, v, v, v, v],
            [args.ott, 21, -4, name, 34000, rights, "cc0 (...)", v, v, v, v, v, v],
            [args.ott, 21, -3, name, 25000, rights, "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 21, -2, name, 30000, rights, "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 21, -1, name, 35000, rights, "cc-by-2.0 (...)", v, v, v, v, v, v],
        ]

        expected_results = (
            (0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 1, 0),
            (0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0),
            (1, 1, 1, 1, 0, 0),
            (1, 0, 1, 0, 0, 0),
            (0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 1, 1),
            (0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0),
            (1, 0, v, 0, 0, 0),
        )
        # fmt: on

        # Insert all the test rows
        ph = placeholder(db)
        for test_row in test_rows:
            db._adapter.execute(self.set_sql.format(ph), [*test_row, datetime.datetime.now()])
        db.commit()

        # Run the function and make sure it made changes
        made_changes = process_image_bits.process_args(args)
        assert made_changes

        # Make sure the database content is as expected
        self.check_database_content(args, expected_results, db)

        # Run the function again and make sure it didn't make any changes this time
        made_changes = process_image_bits.process_args(args)
        assert not made_changes

        # Make sure the database content is still as expected
        self.check_database_content(args, expected_results, db)

        if not keep_rows:
            delete_all_by_ott(db, "images_by_ott", args.ott)
