import datetime
import pytest
import types
from oz_tree_build.utilities.db_helper import connect_to_database, delete_all_by_ott, placeholder
from oz_tree_build.images_and_vernaculars import process_image_bits

@pytest.fixture(scope='session', autouse=True)
def db(appconfig):
    db = connect_to_database(appconfig=appconfig)
    yield db
    db.close()


class TestDBHelper:
    def test_connect_to_database(self, appconfig):
        db = connect_to_database(appconfig=appconfig)
        assert tuple(db.executesql("SELECT 1;")) == ((1, ),)
        assert len(db.executesql("SELECT id from images_by_ott LIMIT 1")) > 0
        assert len(db.executesql("SELECT id from vernacular_by_ott LIMIT 1")) > 0
        assert len(db.executesql("SELECT id from ordered_leaves LIMIT 1")) > 0
        db.close()

class BaseDB:
    get_sql = (
        "SELECT best_any, overall_best_any, best_verified, overall_best_verified, best_pd, overall_best_pd FROM images_by_ott "
        "WHERE ott={0} ORDER BY id;"
    )
    set_sql = (
        "INSERT INTO images_by_ott "
        "(ott,src,src_id,url,rating,rights,licence,best_any,overall_best_any,"
        "best_verified,overall_best_verified,best_pd,overall_best_pd,updated) "
        "VALUES ({0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0});"
    )


class TestAPI(BaseDB):
    ott = -111
    def test_empty(self, db):
        # Delete the test rows before starting the test.
        # We don't delete them at the end, because we want to see the results manually.
        delete_all_by_ott(db, "images_by_ott", self.ott)
        process_image_bits.resolve(db, self.ott)

    def test_single(self, db):
        ott = -111
        ph = placeholder(db)
        # Delete the test rows before starting the test.
        # We don't delete them at the end, because we want to see the results manually.
        delete_all_by_ott(db, "images_by_ott", self.ott)
        test_row = [self.ott, 20, -3, "foo.jpg", 24000, "Unknown", "cc0 (...)", 0, 0, 0, 0, 0, 0]
        sql = self.set_sql.format(ph)
        db.executesql(sql, test_row + [datetime.datetime.now()])
        made_changes = process_image_bits.resolve(db, ott)
        assert made_changes
        sql = self.get_sql.format(ph)
        rows = db.executesql(sql, (self.ott, ))
        assert len(rows) == 1
        assert tuple(rows[0]) == (1, 1, 1, 1, 1, 1)


class TestCLI(BaseDB):
    def check_database_content(self, args, expected_results, db):
        # Query the database and check the results
        rows = db.executesql(self.get_sql.format(placeholder(db)), (args.ott, ))
        for i, row in enumerate(rows):
            assert row == expected_results[i]

    @pytest.mark.parametrize("init_value", [0, 1])
    def test_process_image_bits(self, db, appconfig, init_value):
        args = types.SimpleNamespace(ott=-777, config_file=appconfig)
        # Delete the test rows before starting the test.
        # We don't delete them at the end, because we want to see the results manually.

        delete_all_by_ott(db, "images_by_ott", args.ott)

        v = init_value
        # fmt: off
        test_rows = [
            [args.ott, 20, -1, "foo.jpg", 24000, "Unknown", "cc0 (...)", v, v, v, v, v, v],
            [args.ott, 20, -2, "foo.jpg", 29000, "Unknown", "pd (...)", v, v, v, v, v, v],
            [args.ott, 20, -3, "foo.jpg", 33000, "Unknown", "cc0 (...)", v, v, v, v, v, v],
            [args.ott, 20, -4, "foo.jpg", 25000, "Unknown", "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 20, -4, "foo.jpg", 30000, "Unknown", "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 20, -5, "foo.jpg", 35000, "Unknown", "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 2, -6, "foo.jpg", 28000, "Unknown", "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 21, -6, "foo.jpg", 23000, "Unknown", "cc0 (...)", v, v, v, v, v, v],
            [args.ott, 21, -5, "foo.jpg", 29000, "Unknown", "pd (...)", v, v, v, v, v, v],
            [args.ott, 21, -4, "foo.jpg", 34000, "Unknown", "cc0 (...)", v, v, v, v, v, v],
            [args.ott, 21, -3, "foo.jpg", 25000, "Unknown", "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 21, -2, "foo.jpg", 30000, "Unknown", "cc-by-2.0 (...)", v, v, v, v, v, v],
            [args.ott, 21, -1, "foo.jpg", 35000, "Unknown", "cc-by-2.0 (...)", v, v, v, v, v, v],
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
            (1, 0, 0, 0, 0, 0),
        )
        # fmt: on


        # Insert all the test rows
        ph = placeholder(db)
        for test_row in test_rows:
            db._adapter.execute(self.set_sql.format(ph), test_row + [datetime.datetime.now()])
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

