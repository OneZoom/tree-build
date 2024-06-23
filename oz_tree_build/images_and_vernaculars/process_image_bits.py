import argparse
import logging
from oz_tree_build.utilities.db_helper import connect_to_database, read_config
from oz_tree_build._OZglobals import src_flags

logger = logging.getLogger(__name__)


def is_licence_public_domain(licence):
    return licence.startswith("pd") or licence.startswith("cc0")


def process_args(args):
    global db_connection, datetime_now, subs, db_curs, config

    config = read_config(args.config_file)
    database = config.get("db", "uri")

    db_connection, datetime_now, subs = connect_to_database(database)
    db_curs = db_connection.cursor()

    ott = args.ott

    columns = [
        "id",
        "src",
        "rating",
        "licence",
        "best_any",
        "best_verified",
        "best_pd",
        "overall_best_any",
        "overall_best_verified",
        "overall_best_pd",
    ]
    db_curs.execute(
        "SELECT "
        + ", ".join(columns)
        + " FROM images_by_ott WHERE ott={};".format(subs, subs),
        ott,
    )

    # Turn each row into a dictionary, and get them all into a list
    images = [dict(zip(columns, row)) for row in db_curs.fetchall()]
    # Sort the images by rating descending
    images.sort(key=lambda x: x["rating"], reverse=True)

    # Group the images by their source (each sublist will already be sorted by rating descending)
    images_by_src = {}
    for row in images:
        images_by_src.setdefault(row["src"], []).append(row)

    # Keep track of whether any changes are made, so we know whether to commit them
    made_changes = False

    def set_bit_for_first_image_only(images, column_name, candidate=lambda x: True):
        """
        Set the first row that meets the condition to 1, and all others to 0.
        Returns True if any changes were made.
        """
        nonlocal made_changes
        first = True
        for image in images:
            new_value = 1 if first and candidate(image) else 0
            if image[column_name] != new_value:
                image[column_name] = new_value
                made_changes = True
            if new_value:
                first = False

    # Set the best_any and best_pd bits for each source
    for src, images_for_src in images_by_src.items():
        set_bit_for_first_image_only(images_for_src, "best_any")
        set_bit_for_first_image_only(
            images_for_src,
            "best_pd",
            candidate=lambda row: is_licence_public_domain(row["licence"]),
        )
        set_bit_for_first_image_only(
            images_for_src,
            "best_verified",
            # Images from onezoom_bespoke or wiki are treated as verified, while others are not
            candidate=lambda x: src == src_flags["onezoom_bespoke"]
            or src == src_flags["wiki"],
        )

    # Set the overall_best_any and overall_best_pd bits for all images
    set_bit_for_first_image_only(images, "overall_best_any")
    set_bit_for_first_image_only(
        images, "overall_best_verified", candidate=lambda row: row["best_verified"]
    )
    set_bit_for_first_image_only(
        images, "overall_best_pd", candidate=lambda row: row["best_pd"]
    )

    if made_changes:
        logger.info(f"Updating database since there are changes for ott {ott}")

        for row in images:
            db_curs.execute(
                "UPDATE images_by_ott SET best_any={}, best_verified={}, best_pd={}, overall_best_any={}, overall_best_verified={}, overall_best_pd={} WHERE id={};".format(
                    subs, subs, subs, subs, subs, subs, subs
                ),
                (
                    row["best_any"],
                    row["best_verified"],
                    row["best_pd"],
                    row["overall_best_any"],
                    row["overall_best_verified"],
                    row["overall_best_pd"],
                    row["id"],
                ),
            )
        db_connection.commit()
    else:
        logger.info(f"No changes to make to the database for ott {ott}")

    return made_changes


def main():
    logging.debug("")  # Makes logging work
    logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--config-file",
        default=None,
        help="The configuration file to use. If not given, defaults to private/appconfig.ini",
    )

    parser.add_argument("ott", type=str, help="The leaf ott to process")

    process_args(parser.parse_args())


if __name__ == "__main__":
    main()
