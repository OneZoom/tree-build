import argparse
import logging

from oz_tree_build._OZglobals import src_flags
from oz_tree_build.utilities.db_helper import (
    connect_to_database,
    placeholder,
    read_config,
)

logger = logging.getLogger(__name__)


def is_licence_public_domain(licence):
    return licence.endswith("public domain") or licence.startswith("pd") or licence.startswith("cc0")


def set_bit_for_first_image_only(images, column_name, candidate=lambda x: True):
    """
    Set the first row that meets the condition to 1, and all others to 0.
    Returns `True` if any changes were made.
    """
    # Keep track of whether any changes are made, so we know whether to commit them
    made_changes = False
    first = True
    for image in images:
        new_value = 1 if first and candidate(image) else 0
        if image[column_name] != new_value:
            image[column_name] = new_value
            made_changes = True
        if new_value:
            first = False
    return made_changes


def resolve_from_config(ott, config_file):
    """
    Process image bits for the given ott, getting a new db_context from a config file.
    Returns `True` if any changes were made.
    """
    config = read_config(config_file)
    database = config.get("db", "uri")

    db = connect_to_database(database)
    return resolve(db, ott)


def resolve(db, ott):
    """
    Resolve image bits for the given ott, making sure that only one image is
    marked as the best for each source, and that only one image is marked as
    overall_best for all sources. Returns `True` if any changes were made.
    """
    columns = [
        "id",
        "src",
        "rating",
        "licence",
        "best_any",
        "overall_best_any",
        "best_verified",
        "overall_best_verified",
        "best_pd",
        "overall_best_pd",
    ]
    rows = db.executesql(
        "SELECT " + ", ".join(columns) + f" FROM images_by_ott WHERE ott={placeholder(db)} ORDER BY id;",
        (ott,),
    )

    # Turn each row into a dictionary, and get them all into a list
    images = [dict(zip(columns, row)) for row in rows]
    # Sort the images by rating descending
    images.sort(key=lambda x: x["rating"], reverse=True)

    # Group the images by src (each sublist will already be sorted by rating descending)
    images_by_src = {}
    for row in images:
        images_by_src.setdefault(row["src"], []).append(row)

    made_changes = False
    # Set the best_any and best_pd bits for each source
    for src, images_for_src in images_by_src.items():
        made_changes |= set_bit_for_first_image_only(images_for_src, "best_any")
        made_changes |= set_bit_for_first_image_only(
            images_for_src,
            "best_pd",
            candidate=lambda row: is_licence_public_domain(row["licence"]),
        )
        # NB: sources can be marked as verified, but only if they are already marked as such
        # However, images from onezoom_bespoke or wiki are always treated as verified,
        made_changes |= set_bit_for_first_image_only(
            images_for_src,
            "best_verified",
            candidate=lambda row, src=src: (
                src in (src_flags["wiki"], src_flags["onezoom_bespoke"]) or row["best_verified"] == 1
            ),
        )

    # Set the overall_best_any and overall_best_pd bits for all images
    made_changes |= set_bit_for_first_image_only(images, "overall_best_any")
    made_changes |= set_bit_for_first_image_only(
        images, "overall_best_verified", candidate=lambda row: row["best_verified"]
    )
    made_changes |= set_bit_for_first_image_only(images, "overall_best_pd", candidate=lambda row: row["best_pd"])

    if made_changes:
        logger.info(f"Updating database since there are changes for ott {ott}")

        for row in images:
            db._adapter.execute(
                (
                    f"UPDATE images_by_ott SET best_any={placeholder(db)}, "
                    f"best_verified={placeholder(db)}, "
                    f"best_pd={placeholder(db)}, "
                    f"overall_best_any={placeholder(db)}, "
                    f"overall_best_verified={placeholder(db)}, "
                    f"overall_best_pd={placeholder(db)} "
                    f"WHERE id={placeholder(db)};"
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
        db.commit()
    else:
        logger.info(f"No changes to make to the database for ott {ott}")

    return made_changes


def process_args(args):
    return resolve_from_config(args.ott, args.conf_file)


def main():
    logging.debug("")  # Makes logging work
    logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--conf-file",
        default=None,
        help=("The configuration file to use. " "If not given, defaults to ../../../OZtree/private/appconfig.ini"),
    )

    parser.add_argument("ott", type=str, help="The leaf ott to process")

    process_args(parser.parse_args())


if __name__ == "__main__":
    main()
