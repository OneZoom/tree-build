import types
from oz_tree_build.utilities.db_helper import connect_to_database
from oz_tree_build.images_and_vernaculars import process_image_bits
from tests.db_test_helpers import delete_all_by_ott

db_context = connect_to_database()


def test_process_image_bits():
    args = types.SimpleNamespace(ott=-777, config_file=None)

    # Delete the test rows before starting the test.
    # We don't delete them at the end, because we want to see the results manually.
    delete_all_by_ott(db_context, "images_by_ott", args.ott)

    # fmt: off
    test_rows = [
        [args.ott, 20, 1, "foo.jpg", 24000, "Unknown", "cc0 (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 20, 1, "foo.jpg", 29000, "Unknown", "pd (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 20, 1, "foo.jpg", 33000, "Unknown", "cc0 (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 20, 1, "foo.jpg", 25000, "Unknown", "cc-by-2.0 (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 20, 1, "foo.jpg", 30000, "Unknown", "cc-by-2.0 (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 20, 1, "foo.jpg", 35000, "Unknown", "cc-by-2.0 (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 2, 1, "foo.jpg", 28000, "Unknown", "cc-by-2.0 (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 21, 1, "foo.jpg", 23000, "Unknown", "cc0 (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 21, 1, "foo.jpg", 29000, "Unknown", "pd (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 21, 1, "foo.jpg", 34000, "Unknown", "cc0 (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 21, 1, "foo.jpg", 25000, "Unknown", "cc-by-2.0 (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 21, 1, "foo.jpg", 30000, "Unknown", "cc-by-2.0 (...)", 0, 0, 0, 0, 0, 0],
        [args.ott, 21, 1, "foo.jpg", 35000, "Unknown", "cc-by-2.0 (...)", 0, 0, 0, 0, 0, 0],
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

    def check_database_content():
        # Query the database and check the results
        sql = "SELECT best_any, overall_best_any, best_verified, overall_best_verified, best_pd, overall_best_pd FROM images_by_ott WHERE ott={0} ORDER BY id;"
        db_context.execute(sql, args.ott)
        rows = db_context.db_curs.fetchall()

        for i, row in enumerate(rows):
            assert row == expected_results[i]

    # Insert all the test rows
    for test_row in test_rows:
        sql = "INSERT INTO images_by_ott (ott, src, src_id, url, rating, rights, licence, updated, best_any, overall_best_any, best_verified, overall_best_verified, best_pd, overall_best_pd) VALUES ({0},{0},{0},{0},{0},{0},{0},{1},{0},{0},{0},{0},{0},{0});"
        db_context.execute(sql, test_row)
    db_context.db_connection.commit()

    # Run the function and make sure it made changes
    made_changes = process_image_bits.process_args(args)
    assert made_changes

    # Make sure the database content is as expected
    check_database_content()

    # Run the function again and make sure it didn't make any changes this time
    made_changes = process_image_bits.process_args(args)
    assert not made_changes

    # Make sure the database content is still as expected
    check_database_content()
