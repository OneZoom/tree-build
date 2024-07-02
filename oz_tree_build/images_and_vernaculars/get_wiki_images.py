"""
This utility retrieves images and vernacular names from Wikidata for a given taxon or clade.
"""

"""
It can be called in two ways:
- To process a single taxon, use the 'leaf' subcommand. This will get the image and vernaculars for the given taxon. e.g.
    get_wiki_images.py leaf "Panthera leo"
    get_wiki_images.py leaf "Panthera leo" "File:Panthera leo.jpg"
    get_wiki_images.py leaf "Panthera leo" "File:Panthera leo.jpg" 42000
- To process a full clade, use the 'clade' subcommand. This will get the images and vernaculars for all the taxa in the clade.
    e.g. get_wiki_images.py clade "Panthera" OneZoom_latest-all.json
"""

import argparse
import configparser
import datetime
import json
from io import BytesIO
import logging
import os
from pathlib import Path
import re
import time
import types
import requests
import sys

import urllib.request
from oz_tree_build.images_and_vernaculars import process_image_bits
from oz_tree_build.utilities.file_utils import enumerate_lines_from_file
from oz_tree_build.utilities.db_helper import (
    connect_to_database,
    get_next_src_id_for_src,
    read_config,
    placeholder,
)

from oz_tree_build._OZglobals import src_flags
import time

from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential

from PIL import Image

default_wiki_image_rating = 35000
bespoke_wiki_image_rating = 40000

logger = logging.getLogger(Path(__file__).name)


# Copied from OZTree/OZprivate/ServerScripts/Utilities/getEOL_crops.py
def subdir_name(doID):
    """
    Make a valid subdirectory name in which to save images, based on the last 3 chars of
    the data object ID
    """
    subdir = str(doID)[-3:]
    assert os.path.sep not in subdir
    assert subdir not in (os.curdir, os.pardir)
    return subdir


def make_http_request_with_retries(url):
    """
    Make an HTTP GET request to the given URL with the given headers, retrying if we get a 429 rate limit error.
    """

    # See https://meta.wikimedia.org/wiki/User-Agent_policy
    wiki_http_headers = {
        "User-Agent": "OneZoomBot/0.1 (https://www.onezoom.org/; mail@onezoom.org) get-wiki-images/0.1"
    }

    retries = 6
    delay = 1
    for i in range(retries):
        r = requests.get(url, headers=wiki_http_headers)
        if r.status_code == 200:
            return r

        if r.status_code == 429:
            logger.warning(f"Rate limited on attempt {i+1}")
            time.sleep(delay)
            delay *= 2  # exponential backoff
        else:
            raise Exception(f"Error requesting {url}: {r.status_code} {r.text}")

    raise Exception(f"Failed to get {url} after {retries} attempts")


def get_image_analysis_client(config):
    """
    Given a config object, return an Azure Image Analysis client.
    """
    try:
        azure_vision_endpoint = config.get("azure_vision", "endpoint")
        azure_vision_key = config.get("azure_vision", "key")
    except configparser.NoOptionError:
        logger.error("Azure Vision API key not found in config file")
        sys.exit()

    return ImageAnalysisClient(
        endpoint=azure_vision_endpoint,
        credential=AzureKeyCredential(azure_vision_key),
    )


def get_image_crop_box(image, crop):
    """
    `image` can be a URL or a local file path.
    Get the crop box for an image. If `crop` is an ImageAnalysisClient
    use the Azure Vision API.
    """
    if hasattr(crop, "analyze_from_url"):
        if image.startswith("http"):
            image_analysis_client = crop
            result = image_analysis_client.analyze_from_url(
                image,
                visual_features=[VisualFeatures.SMART_CROPS],
                smart_crops_aspect_ratios=[1.0],
            )
            return result.smart_crops.list[0].bounding_box
        else:
            raise ValueError("Azure Vision API can only be used with URLs")
    else:
        if len(crop) != 4:
            raise ValueError("If given, `crop` must be an ImageAnalysisClient or a tuple of 4 integers")
        return types.SimpleNamespace(x=crop[0], y=crop[1], width=crop[2], height=crop[3])

def get_preferred_or_first_image_from_json_item(json_item):
    """
    Get the first preferred image, or the first image if there are no preferred images, from a Wikidata JSON item.
    """

    # P18 is the property for images
    try:
        images = [
            {
                "name": claim["mainsnak"]["datavalue"]["value"],
                "preferred": 1 if claim["rank"] == "preferred" else 0,
            }
            for claim in json_item["claims"]["P18"]
        ]
    except KeyError as e:
        # Some entries don't have images at all. Others like Q5733335 have a P18 but no images in it.
        return None

    image = next((image for image in images if image["preferred"]), None)
    if not image:
        # Fall back to the first non-preferred image if there are no preferred images
        image = images[0]

    return image


def get_vernaculars_by_language_from_json_item(json_item):
    """
    Get the vernacular names from a Wikidata JSON item for all languages.
    """

    vernaculars_by_language = {}
    known_canonical_vernaculars = set()

    # P1843 is the property for vernacular names
    try:
        for claim in json_item["claims"]["P1843"]:
            language = claim["mainsnak"]["datavalue"]["value"]["language"]

            vernacular_info = {
                "name": claim["mainsnak"]["datavalue"]["value"]["text"],
                "preferred": 1 if claim["rank"] == "preferred" else 0,
            }

            # There are often multiple vernaculars that only differ in case or punctuation.
            # We only want to keep one of each for a given language.
            canonical_vernacular = (
                language
                + ","
                + "".join(filter(str.isalnum, vernacular_info["name"])).lower()
            )
            if canonical_vernacular in known_canonical_vernaculars:
                continue
            known_canonical_vernaculars.add(canonical_vernacular)

            vernaculars_by_language.setdefault(language, []).append(vernacular_info)
    except (KeyError, IndexError):
        return None

    # For each language:
    # - We keep all the vernaculars
    # - If none are marked as preferred, the first non-referred will be marked as preferred
    # - If multiple are marked as preferred, the first one will be kept as preferred
    for vernaculars in vernaculars_by_language.values():
        vernaculars.sort(reverse = True, key = lambda v: v["preferred"])
        for i, v in enumerate(vernaculars):
            v["preferred"] = 1 if i == 0 else 0
    return vernaculars_by_language


def enumerate_dump_items_with_images_or_vernaculars(wikipedia_dump_file):
    """
    Enumerate the items in a Wikidata JSON dump that have images.
    """

    for _, line in enumerate_lines_from_file(wikipedia_dump_file):
        if not (line.startswith('{"type":')):
            continue
        json_item = json.loads(line.rstrip().rstrip(","))

        image = get_preferred_or_first_image_from_json_item(json_item)
        vernaculars_by_language = get_vernaculars_by_language_from_json_item(json_item)
        if image or vernaculars_by_language:
            qid = int(json_item["id"][1:])
            yield qid, image, vernaculars_by_language


def get_wikidata_json_for_qid(qid):
    """
    Use the Wikidata API to get the JSON for a given QID.
    This is faster than using the dump file when we only need a single item.
    Worth noting that this gets the latest version of the item, which may not be the same as the dump file.
    """

    wikidata_url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q{qid}&format=json"

    r = make_http_request_with_retries(wikidata_url)

    json = r.json()
    return json["entities"][f"Q{qid}"]


def get_image_license_info(escaped_image_name):
    """
    Use the Wikimedia API to get the license and artist for a Wikimedia image.
    """

    image_metadata_url = f"https://api.wikimedia.org/w/api.php?action=query&prop=imageinfo&iiprop=extmetadata&titles=File%3a{escaped_image_name}&format=json&iiextmetadatafilter=License|LicenseUrl|Artist"

    r = make_http_request_with_retries(image_metadata_url)
    try:
        extmetadata = r.json()["query"]["pages"]["-1"]["imageinfo"][0]["extmetadata"]
    except KeyError:
        logger.warning(f"Unknown image '{escaped_image_name}'")
        return None

    license_info = {}

    try:
        license_info["license_url"] = extmetadata["LicenseUrl"]["value"]
    except KeyError:
        # Public domain images typically don't have a license URL
        license_info["license_url"] = None

    try:
        if "Artist" in extmetadata:
            license_info["artist"] = extmetadata["Artist"]["value"]
            # Strip the html tags from the artist
            license_info["artist"] = re.sub(r"<[^>]*>", "", license_info["artist"])
        else:
            license_info["artist"] = "Unknown artist"

        # Some images have a flicker common license URL but not License field (e.g. Potos_flavus_(22985770100).jpg)
        # We treat these as public domain, because the flicker common license is basically that.
        if (
            not "License" in extmetadata
            and license_info["license_url"] == "https://www.flickr.com/commons/usage/"
        ):
            license_info["license"] = "pd"
        else:
            license_info["license"] = extmetadata["License"]["value"]

        # If the license doesn't start with "cc" or "pd", we can't use it
        if not license_info["license"].startswith("cc") and not license_info[
            "license"
        ].startswith("pd"):
            logger.warning(
                f"Unacceptable license for '{escaped_image_name}': {license_info['license']}"
            )
            return None
    except KeyError:
        return None

    return license_info


def get_image_url(escaped_image_name):
    """
    Use the wikimedia API to get the image URL for a given image name.
    """

    # This returns JSON that contains the actual image URLs in various sizes
    image_location_url = (
        f"https://api.wikimedia.org/core/v1/commons/file/{escaped_image_name}"
    )

    r = make_http_request_with_retries(image_location_url)

    image_location_info = r.json()
    # Note that 'preferred' here refers to the preferred image *size*, not the preferred image itself
    image_url = image_location_info["preferred"]["url"]

    return image_url


def save_wiki_image(
    db, ott, image, src, src_id, rating, output_dir, crop=None, check_if_up_to_date=True
):
    """
    Download a Wikimedia image for a given QID and save it to the output directory.
    We keep both the uncropped and cropped versions of the image, along with the crop info.
    `crop` can be an Azure ImageAnalysisClient, a crop location in the image (x, y, width, height),
    or None to carry out a default (centered) crop.
    """

    wiki_image_url_prefix = "https://commons.wikimedia.org/wiki/File:"
    ph = placeholder(db)

    # Wikimedia uses underscores instead of spaces in URLs
    escaped_image_name = image["name"].replace(" ", "_")

    if check_if_up_to_date:
        # If we already have an image for this taxon, and it's the same as the one we're trying to download, skip it
        row = db.executesql(
            "SELECT url FROM images_by_ott WHERE src={0} and ott={0};".format(ph),
            (src, ott),
        )
        if len(row) > 0:
            url = row[0][0]
            existing_image_name = url[len(wiki_image_url_prefix) :]
            if existing_image_name == escaped_image_name:
                logger.info(f"Image for {ott} is already up to date: {image['name']}")
                return

    logger.info(f"Processing image for ott={ott} (qid={src_id}): {image['name']}")

    license_info = get_image_license_info(escaped_image_name)
    if not license_info:
        logger.warning(
            f"Couldn't get license or artist for '{escaped_image_name};. Ignoring it."
        )
        return False

    is_public_domain = license_info["license"] in {"pd", "cc0"}
    license_string = (
        f"{license_info['license']} ({license_info['license_url']})"
        if license_info["license_url"]
        else license_info["license"]
    )

    image_url = get_image_url(escaped_image_name)

    # We use the qid as the source id. This is convenient, although it does mean
    # that we can't have two wikidata images for a given taxon.
    image_dir = os.path.join(output_dir, str(src), subdir_name(src_id))
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    # Download the uncropped image
    uncropped_image_path = f"{image_dir}/{src_id}_uncropped.jpg"
    urllib.request.urlretrieve(image_url, uncropped_image_path)

    if crop is None:
        # Default to centering the crop
        img = Image.open(uncropped_image_path)
        w, h = img.size
        square_dim = min(w, h)
        crop = ((w - square_dim) // 2, (h - square_dim) // 2, square_dim, square_dim)
    # Get the crop box e.g. using the Azure Vision API
    crop_box = get_image_crop_box(image_url, crop)

    # Crop and resize the image using PIL
    im = Image.open(uncropped_image_path)
    # Convert to RGB to avoid issues with transparency when working with a png file
    if im.mode in ("RGBA", "P"):
        im = im.convert("RGB")
    im = im.resize(
        (300, 300),
        box=(
            crop_box.x,
            crop_box.y,
            crop_box.x + crop_box.width,
            crop_box.y + crop_box.height,
        ),
    )
    im.save(f"{image_dir}/{src_id}.jpg")

    # Save the crop info in a text file next to the image
    crop_info_path = f"{image_dir}/{src_id}_cropinfo.txt"
    with open(crop_info_path, "w") as f:
        f.write(f"{crop_box.x},{crop_box.y},{crop_box.width},{crop_box.height}")

    # Delete any existing wiki images for this taxon from the database
    # Note that we don't do this for bespoke images, as there can be multiple for a given taxon
    if src == src_flags["wiki"]:
        sql = "DELETE FROM images_by_ott WHERE ott={0} and src={0};".format(ph)
        db.executesql(sql, (ott, src))

    # Insert the new image into the database
    wikimedia_url = f"https://commons.wikimedia.org/wiki/File:{escaped_image_name}"
    db.executesql(
        "INSERT INTO images_by_ott "
        "(ott,src,src_id,url,rating,rating_confidence,best_any,best_verified,best_pd,"
        "overall_best_any,overall_best_verified,overall_best_pd,rights,licence,updated) "
        "VALUES ({0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0},{0});".format(ph),
        (
            ott,
            src,
            src_id,
            wikimedia_url,
            rating,
            None,
            1,  # We only have one for the given src, so it's the best
            1,  # We're assuming that all wiki images are verified (i.e. shows correct species)
            (
                1 if is_public_domain else 0
            ),  # Only set this to 1 if the image is public domain
            1,
            1,
            1,  # These will need to be adjusted based on all images for the taxon
            license_info["artist"],
            license_string,
            datetime.datetime.now(),
        ),
    )

    # Since we added a new image, we need to update all the image bits for that ott
    process_image_bits.resolve(db, ott)

    return True


def save_all_wiki_vernaculars_for_qid(db, ott, qid, vernaculars_by_language):
    """
    Save all vernacular names for a given QID to the database.
    Note that there can be multiple vernaculars for one language (e.g. "Lion" and "Africa Lion")
    """
    ph = placeholder(db)
    # Delete any existing wiki vernaculars for this taxon from the database
    sql = "DELETE FROM vernacular_by_ott WHERE ott={0} and src={0};".format(ph)
    db.executesql(sql, (ott, src_flags["wiki"]))

    for language, vernaculars in vernaculars_by_language.items():
        # The wikidata language could either be a full language code (e.g. "en-us") or just the primary code (e.g. "en")
        # We need to make sure that lang_primary is just the primary code
        lang_primary = language.split("-")[0]

        for vernacular in vernaculars:
            # We only want to flag the first preferred vernacular for this source as preferred
            logger.info(
                f"Setting '{language}' vernacular for ott={ott} (qid={qid}, preferred={vernacular['preferred']}): {vernacular['name']}"
            )

            # Insert the new vernacular into the database
            sql = (
                "INSERT INTO vernacular_by_ott "
                "(ott, vernacular, lang_primary, lang_full, preferred, src, src_id, updated)"
                " VALUES ({0},{0},{0},{0},{0},{0},{0},{0});".format(ph)
            )
            db._adapter.execute(  # alternative to executesql that doesn't commit
                sql,
                (
                    ott,
                    vernacular["name"],
                    lang_primary,
                    language,
                    vernacular["preferred"],
                    src_flags["wiki"],
                    qid,
                    datetime.datetime.now()
                ),
            )

    db.commit()


def process_leaf(
    db,
    ott_or_taxon,
    image_name=None,
    rating=None,
    skip_images=None,
    output_dir=None,
    crop=None
):
    """
    If ott_or_taxon is a number, it's an ott. Otherwise, it's a taxon name.
    `crop` can be an Azure ImageAnalysisClient, a crop location in the image (x, y, width, height),
    or None to carry out a default (centered) crop.
    """
    # Real otts are never negative, but we abuse them in our tests, so account for that.
    ph = placeholder(db)
    sql = "SELECT ott,wikidata,name FROM ordered_leaves WHERE "
    if ott_or_taxon.lstrip("-").isnumeric():
        sql += f"ott={ph};"
    else:
        sql += f"name={ph};"

    try:
        result = db.executesql(sql, (ott_or_taxon, ))
        if len(result) > 1:
            raise ValueError(f"Multiple results for '{ott_or_taxon}'")
        (ott, qid, name) = result[0]
    except TypeError:
        logger.error(f"'{ott_or_taxon}' not found in ordered_leaves table")
        return

    logger.info(f"Processing '{name}' (ott={ott}, qid={qid})")

    # Three cases for the rating:
    # - If it's passed in for a bespoke image, use it
    # - If it's not passed in for a bespoke image, use 40000
    # - for non-bespoke images, use 35000
    if rating is None:
        rating = bespoke_wiki_image_rating if image_name else default_wiki_image_rating

    json_item = get_wikidata_json_for_qid(qid)

    if not skip_images:
        # If a specific image name is passed in, use it. Otherwise, we need to look it up.
        # Also, if an image is passed in, we categorize it as a bespoke image, not wiki.
        if image_name:
            image = {"name": image_name}
            src = src_flags["onezoom_bespoke"]

            # Get the highest bespoke src_id, and add 1 to it for the new image src_id
            src_id = get_next_src_id_for_src(db, src)
        else:
            image = get_preferred_or_first_image_from_json_item(json_item)
            src = src_flags["wiki"]
            src_id = qid
        if image:
            save_wiki_image(db, ott, image, src, src_id, rating, output_dir, crop)

    vernaculars_by_language = get_vernaculars_by_language_from_json_item(json_item)
    save_all_wiki_vernaculars_for_qid(db, ott, qid, vernaculars_by_language)


def process_clade(db, ott_or_taxon, dump_file, skip_images, output_dir, crop=None):
    """
    `crop` can be an ImageAnalysisClient, a crop location in the image (x, y, width, height),
    or None to carry out a default (centered) crop.
    """
    ph = placeholder(db)
    # Get the left and right leaf ids for the passed in taxon
    sql = "SELECT leaf_lft,leaf_rgt FROM ordered_nodes WHERE "
    # If ott_or_taxon is a number, it's an ott. If it's a string, it's a taxon name.
    if ott_or_taxon.isnumeric():
        sql += "ott={0};"
    else:
        sql += "name={0};"
    try:
        rows = db.executesql(sql, (ott_or_taxon,))
    except TypeError:
        logger.error(f"'{ott_or_taxon}' not found in ordered_nodes table")
        if len(rows) > 1:
            logger.error(f"Multiple results for '{ott_or_taxon}'")
            return
        (leaf_left, leaf_right) = rows[0]

    if not skip_images:
        # Find all the leaves in the clade that don't have wiki images (ignoring images from other sources)
        sql = """
        SELECT wikidata, ordered_leaves.ott FROM ordered_leaves
        LEFT OUTER JOIN (SELECT ott,src,url FROM images_by_ott WHERE src={0}) as wiki_images_by_ott ON ordered_leaves.ott=wiki_images_by_ott.ott
        WHERE url IS NULL AND ordered_leaves.id >= {0} AND ordered_leaves.id <= {0};
        """.format(ph)
        leaves_without_images = dict(
            db.execute_sql(sql, (src_flags["wiki"], leaf_left, leaf_right))
        )
        logger.info(
            f"Found {len(leaves_without_images)} taxa without an image in the database"
        )

    # Find all the leaves in the clade that don't have wiki vernaculars (ignoring vernaculars from other sources)
    sql = """
    SELECT wikidata, ordered_leaves.ott FROM ordered_leaves
    LEFT OUTER JOIN (SELECT ott,src,vernacular FROM vernacular_by_ott WHERE src={0}) as wiki_vernacular_by_ott ON ordered_leaves.ott=wiki_vernacular_by_ott.ott
    WHERE vernacular IS NULL AND ordered_leaves.id >= {0} AND ordered_leaves.id <= {0};
    """.format(ph)
    leaves_without_vernaculars = dict(
        db.executesql(sql, (src_flags["wiki"], leaf_left, leaf_right)))
    logger.info(
        f"Found {len(leaves_without_vernaculars)} taxa without a vernacular in the database"
    )

    leaves_that_got_images = set()
    for qid, image, vernaculars in enumerate_dump_items_with_images_or_vernaculars(
        dump_file
    ):
        if not skip_images and image and qid in leaves_without_images:
            if save_wiki_image(
                db,
                leaves_without_images[qid],
                image,
                src_flags["wiki"],
                qid,
                default_wiki_image_rating,
                output_dir,
                crop,
                check_if_up_to_date=False,
            ):
                leaves_that_got_images.add(qid)
        if vernaculars and qid in leaves_without_vernaculars:
            save_all_wiki_vernaculars_for_qid(
                leaves_without_vernaculars[qid], qid, vernaculars
            )

    # Log the leaves for which we couldn't find images
    logger.info("Taxa for which we couldn't find a proper image:")
    for qid, ott in leaves_without_images.items():
        if qid not in leaves_that_got_images:
            logger.info(f"  ott={ott} qid={qid}")


def process_args(args):
    outdir = args.output_dir
    ott_or_taxon = args.ott_or_taxon
    config = read_config(args.config_file)
    database = config.get("db", "uri")

    # Default to the static folder in the OZtree repo
    if outdir is None:
        outdir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            os.pardir,
            os.pardir,
            os.pardir,
            "OZtree",
            "static",
            "FinalOutputs",
            "img",
        )

    db = connect_to_database(database)
    azure = get_image_analysis_client(config)

    if args.subcommand == "leaf":
        # Process one leaf, optionally forcing the specified image
        process_leaf(db, ott_or_taxon, args.image, args.rating, args.skip_images, outdir, crop=azure)
    elif args.subcommand == "clade":
        # Process all the images in the passed in clade
        process_clade(db, ott_or_taxon, args.dump_file, args.skip_images, outdir, crop=azure)


def main():
    logging.debug("")  # Makes logging work
    logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)

    subparsers = parser.add_subparsers(help="help for subcommand", dest="subcommand")

    def add_common_args(parser):
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Only process vernaculars, not images",
        )
        parser.add_argument(
            "--output-dir",
            "-o",
            default=None,
            help="The location to save the cropped pictures (e.g. 'FinalOutputs/img'). If not given, defaults to ../../../static/FinalOutputs/img (relative to the script location). Files will be saved under output_dir/{src_flag}/{3-digits}/fn.jpg",
        )
        parser.add_argument(
            "--config-file",
            default=None,
            help="The configuration file to use. If not given, defaults to private/appconfig.ini",
        )

    parser_leaf = subparsers.add_parser("leaf", help="Process a single ott")
    parser_leaf.add_argument(
        "ott_or_taxon", type=str, help="The leaf ott or taxon to process"
    )
    parser_leaf.add_argument(
        "image", nargs="?", type=str, help="The image to use for the given ott"
    )
    parser_leaf.add_argument(
        "rating",
        nargs="?",
        type=int,
        help="The rating for the image (defaults to 40000)",
    )
    add_common_args(parser_leaf)

    parser_clade = subparsers.add_parser("clade", help="Process a full clade")
    parser_clade.add_argument(
        "ott_or_taxon", type=str, help="The ott or taxon of the root of the clade"
    )
    parser_clade.add_argument(
        "dump_file",
        type=str,
        help="The wikidata JSON dump from which to get the images",
    )
    add_common_args(parser_clade)

    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        sys.exit()

    process_args(args)


if __name__ == "__main__":
    main()
