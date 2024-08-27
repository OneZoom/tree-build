"""
This utility retrieves images and vernacular names from Wikidata for a given set
of taxa or tips in a clade.

It can be called in two ways:
- To process a single taxon, use the 'leaf' subcommand. This will get the image and
  vernaculars for the given taxon. e.g.
    * get_wiki_images.py leaf "Panthera leo"
    * get_wiki_images.py leaf "Panthera leo" "File:Panthera leo.jpg"
    * get_wiki_images.py leaf "Panthera leo" "File:Panthera leo.jpg" 42000
- To process a full clade, use the 'clade' subcommand. This will get the images and
  vernaculars for all the taxa in the clade, e.g.
    * get_wiki_images.py clade "Panthera" OneZoom_latest-all.json
"""

import argparse
import datetime
import json
import logging
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import requests
from PIL import Image

from oz_tree_build._OZglobals import src_flags
from oz_tree_build.images_and_vernaculars import process_image_bits
from oz_tree_build.utilities.db_helper import (
    connect_to_database,
    get_next_src_id_for_src,
    placeholder,
    read_config,
)
from oz_tree_build.utilities.file_utils import enumerate_lines_from_file

from .image_cropping import AzureImageCropper, CenterImageCropper

default_wiki_image_rating = 35000
bespoke_wiki_image_rating = 40000

logger = logging.getLogger(Path(__file__).name)


# Copied from OZTree/OZprivate/ServerScripts/Utilities/getEOL_crops.py
def subdir_name(doID):
    """
    Make a valid subdirectory name in which to save images, based on the last
    3 chars of the data object ID
    """
    subdir = str(doID)[-3:]
    assert os.path.sep not in subdir
    assert subdir not in (os.curdir, os.pardir)
    return subdir


def make_http_request_with_retries(url):
    """
    Make an HTTP GET request to the given URL with the given headers,
    retrying if we get a 429 rate limit error.
    """

    # See https://meta.wikimedia.org/wiki/User-Agent_policy
    wiki_http_headers = {
        "User-Agent": "OneZoomBot/0.1 (https://www.onezoom.org/; " "mail@onezoom.org) get-wiki-images/0.1"
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


def get_preferred_or_first_image_from_json_item(json_item):
    """
    Get the first preferred image from a Wikidata JSON item
    (or the first image if there are no preferred images)
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
    except KeyError:
        # Some entries have no P18. Others like Q5733335 have a P18 but no images in it
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

            # Often multiple vernaculars exist that only differ in case or punctuation.
            # We only want to keep one of each for a given language.
            canonical_vernacular = language + "," + "".join(filter(str.isalnum, vernacular_info["name"])).lower()
            if canonical_vernacular in known_canonical_vernaculars:
                continue
            known_canonical_vernaculars.add(canonical_vernacular)

            vernaculars_by_language.setdefault(language, []).append(vernacular_info)
    except (KeyError, IndexError):
        return vernaculars_by_language

    # For each language:
    # - We keep all the vernaculars
    # - If none are marked as preferred, use the first non-preferred as preferred
    # - If multiple are marked as preferred, the first one will be kept as preferred
    for vernaculars in vernaculars_by_language.values():
        vernaculars.sort(reverse=True, key=lambda v: v["preferred"])
        for i, v in enumerate(vernaculars):
            v["preferred"] = 1 if i == 0 else 0
    return vernaculars_by_language


def enumerate_wiki_dump_items(wikidata_dump_file):
    """
    Enumerate the items in a Wikidata JSON dump that have images.
    """

    for _, line in enumerate_lines_from_file(wikidata_dump_file):
        if not (line.startswith('{"type":')):
            continue
        json_item = json.loads(line.rstrip().rstrip(","))

        image = get_preferred_or_first_image_from_json_item(json_item)
        vernaculars_by_language = get_vernaculars_by_language_from_json_item(json_item)
        qid = int(json_item["id"][1:])
        yield qid, image, vernaculars_by_language


def get_wikidata_json_for_qid(qid):
    """
    Use the Wikidata API to get the JSON for a given QID. This is faster than
    using the dump file when we only need a single item. It's worth noting that this
    gets the latest version of the item, which may not be the same as the dump file.
    """

    wikidata_url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q{qid}&format=json"

    r = make_http_request_with_retries(wikidata_url)

    json = r.json()
    return json["entities"][f"Q{qid}"]


def get_image_license_info(escaped_image_name):
    """
    Use the Wikimedia API to get the license and artist for a Wikimedia image.
    """

    image_metadata_url = (
        "https://api.wikimedia.org/w/api.php"
        f"?action=query&titles=File%3a{escaped_image_name}&format=json&prop=imageinfo"
        "&iiprop=extmetadata&iiextmetadatafilter=License|LicenseUrl|Artist"
    )
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
            license_info["artist"] = re.sub(r"<[^>]*>", "", license_info["artist"]).strip()
        else:
            logger.warning(f"Artist not found for '{escaped_image_name}': using 'Unknown artist'")
            license_info["artist"] = "Unknown artist"

        # Some images have a flickr common license URL but not License field, meaning
        # "No known copyright restrictions"==pd (e.g. Potos_flavus_(22985770100).jpg)
        # TODO, generalise this to other appropriate licenses, e.g. using a dict:
        # {
        #     "https://www.flickr.com/commons/usage/": (
        #          "Flickr commons",
        #          "Marked on Flickr commmons as being in the public domain",
        #     ),
        #     "http://artlibre.org/licence/lal/en": (
        #         "cc-by-sa-4.0",
        #         None,
        #     ),
        # }
        if license_info["license_url"] == "https://www.flickr.com/commons/usage/":
            license_info["license"] = "flickr_commons"
        if license_info["license_url"] == "http://artlibre.org/licence/lal/en":
            # See https://en.wikipedia.org/wiki/Free_Art_License
            license_info["license"] = "cc-by-sa-4.0"
        else:
            license_info["license"] = extmetadata["License"]["value"]

        # If the license doesn't start with "cc" or "pd", we can't use it
        li = license_info["license"].lower()
        if not li.startswith("cc") and not li.startswith("pd") and not li == "flickr_commons":
            logger.warning(f"Unacceptable license for '{escaped_image_name}': {li}")
            return None
    except KeyError:
        return None

    return license_info


def get_image_url(escaped_image_name):
    """
    Use the wikimedia API to get the image URL for a given image name.
    """

    # This returns JSON that contains the actual image URLs in various sizes
    image_location_url = f"https://api.wikimedia.org/core/v1/commons/file/{escaped_image_name}"

    r = make_http_request_with_retries(image_location_url)

    image_location_info = r.json()
    # Note that 'preferred' here refers to the preferred image *size*
    # not the preferred image itself
    image_url = image_location_info["preferred"]["url"]

    return image_url


def save_wiki_image(db, leaf_data, image_name, src, src_id, rating, output_dir, cropper):
    """
    Download a Wikimedia image for a given QID and save it to the output directory. We
    keep both the uncropped and cropped versions of the image, along with the crop info.
    `crop` can be an Azure ImageAnalysisClient, a crop location in the image
    (x, y, width, height), or None to carry out a default (centered) crop.
    """

    wiki_image_url_prefix = "https://commons.wikimedia.org/wiki/File:"
    s = placeholder(db)

    ott = leaf_data["ott"]

    # Wikimedia uses underscores instead of spaces in URLs
    escaped_image_name = image_name.replace(" ", "_")
    image_dir = os.path.normpath(os.path.join(output_dir, str(src), subdir_name(src_id)))
    image_path = f"{image_dir}/{src_id}.jpg"

    # If we already have an image for this taxon, and it's the same as the one
    # we're trying to download, skip it
    if leaf_data["img"]:
        assert leaf_data["img"].startswith(wiki_image_url_prefix)
        existing_image_name = leaf_data["img"][len(wiki_image_url_prefix) :]
        if existing_image_name == escaped_image_name:
            if os.path.isfile(image_path):
                logger.info(f"Image '{image_name}' for {ott} is in the db, and at {image_path}")
                return True
            else:
                logger.warning(f"{image_name} for {ott} is in the db, but the " f"file is missing, so re-processing")

    logger.info(f"Processing image for ott={ott} (qid={src_id}): {image_name}")

    license_info = get_image_license_info(escaped_image_name)
    if not license_info:
        logger.warning(f"Couldn't get license or artist for '{escaped_image_name};. Ignoring it.")
        return False

    is_public_domain = True
    # NB keep all pd strings as ending with the words "public domain"
    if license_info["license"].startswith("pd"):
        license_string = "Marked as being in the public domain"
    elif license_info["license"] == "flickr_commons":
        license_string = "Marked on Flickr commons as being in the public domain"
    elif license_info["license"] == "cc0":
        license_string = "Released into the public domain"
    else:
        is_public_domain = False
        license_string = license_info["license"]
        if license_info.get("license_url"):
            license_string += f" ({license_info['license_url']})"
        # prefix a copyright symbol to the artist
        prefix = "© "
        for skip in ["©", "No machine-readable", "Unknown"]:
            if license_info["artist"].startswith(skip):
                prefix = ""
                break
        license_info["artist"] = prefix + license_info["artist"]

    image_url = get_image_url(escaped_image_name)

    # For src=20 we use the qid as the source id. This is convenient, although it does
    # mean that we can't have two src=20 wikidata images for a given taxon.
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    # Download the uncropped image
    uncropped_image_path = f"{image_dir}/{src_id}_uncropped.jpg"
    urllib.request.urlretrieve(image_url, uncropped_image_path)

    if cropper is None:
        # Default to centering the crop
        cropper = CenterImageCropper()

    # Get the crop box e.g. using the Azure Vision API
    crop_box = cropper.crop(image_url, uncropped_image_path)

    # Crop and resize the image using PIL
    im = Image.open(uncropped_image_path)
    # Convert to RGB to avoid issues with transparency when working with a png file
    if im.mode in ("RGBA", "P", "LA"):
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
    try:
        im.save(image_path)
    except Exception as e:
        logger.warning(f"Error saving {image_path}: {e}")
        return False

    logger.info(f"Saved {image_name} for ott={ott} (Q{src_id}) in {image_path}")

    # Save the crop info in a text file next to the image
    crop_info_path = f"{image_dir}/{src_id}_cropinfo.txt"
    with open(crop_info_path, "w") as f:
        f.write(f"{crop_box.x},{crop_box.y},{crop_box.width},{crop_box.height}")

    # Delete any existing wiki images for this taxon from the database
    # We don't do this for bespoke images, as there can be multiple for a given taxon
    if src == src_flags["wiki"]:
        sql = f"DELETE FROM images_by_ott WHERE ott={s} and src={s};"
        db.executesql(sql, (ott, src))

    # Insert the new image into the database
    wikimedia_url = f"{wiki_image_url_prefix}{escaped_image_name}"
    db.executesql(
        "INSERT INTO images_by_ott "
        "(ott,src,src_id,url,rating,rating_confidence,best_any,best_verified,best_pd,"
        "overall_best_any,overall_best_verified,overall_best_pd,rights,licence,updated) "
        f"VALUES ({s},{s},{s},{s},{s},{s},{s},{s},{s},{s},{s},{s},{s},{s},{s});",
        (
            ott,
            src,
            src_id,
            wikimedia_url,
            rating,
            None,
            1,  # We only have one for the given src, so it's the best
            1,  # We're assuming that all wiki images are verified (i.e. correctly IDed)
            (1 if is_public_domain else 0),  # Only set this to 1 if the image is public domain
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


def save_wiki_vernaculars_for_qid(db, ott, qid, vernaculars_by_language):
    """
    Save all vernacular names for a given QID to the database. Note that there
    can be multiple vernaculars for one language (e.g. "Lion" and "Africa Lion")
    """
    s = placeholder(db)
    # Delete any existing wiki vernaculars for this taxon from the database
    sql = f"DELETE FROM vernacular_by_ott WHERE ott={s} and src={s};"
    db.executesql(sql, (ott, src_flags["wiki"]))

    for language, vernaculars in vernaculars_by_language.items():
        # The wikidata language could either be a full language code (e.g. "en-us")
        # or just the primary code (e.g. "en"): make lang_primary just the primary code
        lang_primary = language.split("-")[0]

        for vernacular in vernaculars:
            # Only flag the first preferred vernacular for this source as preferred
            logger.info(
                f"Setting '{language}' vernacular for ott={ott} (qid={qid}, "
                f"preferred={vernacular['preferred']}): {vernacular['name']}"
            )

            # Insert the new vernacular into the database
            sql = (
                "INSERT INTO vernacular_by_ott "
                "(ott, vernacular, lang_primary, lang_full, preferred, src, src_id, "
                f"updated) VALUES ({s},{s},{s},{s},{s},{s},{s},{s});"
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
                    datetime.datetime.now(),
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
    cropper=None,
):
    """
    If ott_or_taxon is a number it's an ott, otherwise it's a taxon name. `crop` can be
    an Azure ImageAnalysisClient, a crop location in the image (x, y, width, height),
    or None to carry out a default (centered) crop.
    """
    # Real otts are never negative, but we abuse them in our tests, so account for that.
    s = placeholder(db)
    sql = "SELECT ott,wikidata,name FROM ordered_leaves WHERE "
    if ott_or_taxon.lstrip("-").isnumeric():
        sql += f"ott={s};"
    else:
        sql += f"name={s};"

    result = db.executesql(sql, (ott_or_taxon,))
    if len(result) > 1:
        logger.error(f"Multiple results for '{ott_or_taxon}'")
        return
    if len(result) == 0:
        logger.error(f"'{ott_or_taxon}' not found in ordered_leaves table")
        return

    (ott, qid, name) = result[0]
    logger.info(f"Processing '{name}' (ott={ott}, qid={qid})")

    # Three cases for the rating:
    # - If it's passed in, use it
    # - If it's not passed in for a bespoke image, use 40000
    # - for non-bespoke images, use 35000
    if rating is None:
        rating = bespoke_wiki_image_rating if image_name else default_wiki_image_rating

    json_item = get_wikidata_json_for_qid(qid)
    if not skip_images:
        # If a specific image name is passed in (corresponding to a image name on
        # wikimedia commons), we use that. Otherwise, we need to look it up.
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
            leaf_data = {"ott": ott, "taxon": name, "img": None}
            save_wiki_image(db, leaf_data, image["name"], src, src_id, rating, output_dir, cropper)

    vernaculars_by_language = get_vernaculars_by_language_from_json_item(json_item)
    save_wiki_vernaculars_for_qid(db, ott, qid, vernaculars_by_language)


def get_image_from_taxa_data(taxa_data, taxon):
    """
    Get the image for a taxon from the taxa data dictionary.
    """
    if taxon in taxa_data:
        data = taxa_data[taxon]
        if not data:
            return None
        if "redirect" in data:
            data = taxa_data[data["redirect"]]
        if "image" in data:
            return data["image"]
    return None


def process_clade(db, ott_or_taxon, dump_file, taxa_data, skip_images, output_dir, cropper=None):
    """
    `crop` can be an ImageAnalysisClient, a crop location in the image
    (x, y, width, height), or None to carry out a default (centered) crop.
    """
    s = placeholder(db)
    # Get the left and right leaf ids for the passed in taxon
    sql = "SELECT leaf_lft,leaf_rgt,ott FROM ordered_nodes WHERE "
    # If ott_or_taxon is a number, it's an ott. If it's a string, it's a taxon name.
    if ott_or_taxon.isnumeric():
        sql += "ott={0};"
    else:
        sql += "name={0};"
    rows = db.executesql(sql.format(s), (ott_or_taxon,))
    if len(rows) == 0:
        raise ValueError(f"'{ott_or_taxon}' not found in ordered_nodes table")
    if len(rows) > 1:
        logger.error(f"Multiple results for '{ott_or_taxon}', " f"choose out of these OTTs: {[r[2] for r in rows]}")
        return
    (leaf_lft, leaf_rgt, ott) = rows[0]

    if not skip_images:
        # Get all leaves in the clade along with their wiki image, if any
        sql = f"""
        SELECT wikidata, ordered_leaves.ott, name, url FROM ordered_leaves
        LEFT OUTER JOIN (SELECT ott,src,url FROM images_by_ott
        WHERE src={s}) as wiki_images_by_ott ON ordered_leaves.ott=wiki_images_by_ott.ott
        WHERE ordered_leaves.id >= {s} AND ordered_leaves.id <= {s};
        """
        rows = db.executesql(sql, (src_flags["wiki"], leaf_lft, leaf_rgt))
        leaves_data = {qid: {"ott": ott, "taxon": name, "img": url} for qid, ott, name, url in rows}
        logger.info(f"Found {len(leaves_data)} leaves in the database")

    # Get leaves in the clade with no wiki vernaculars, ignoring verns from other sources
    sql = f"""
    SELECT wikidata, ordered_leaves.ott FROM ordered_leaves
    LEFT OUTER JOIN (SELECT ott,src,vernacular FROM vernacular_by_ott WHERE src={s})
    as wiki_vernacular_by_ott ON ordered_leaves.ott=wiki_vernacular_by_ott.ott
    WHERE vernacular IS NULL AND ordered_leaves.id >= {s} AND ordered_leaves.id <= {s};
    """
    leaves_without_vn = dict(db.executesql(sql, (src_flags["wiki"], leaf_lft, leaf_rgt)))
    logger.info(f"Found {len(leaves_without_vn)} taxa without a vernacular in the database")

    leaves_that_got_images = set()
    for qid, image, vernaculars in enumerate_wiki_dump_items(dump_file):
        if not skip_images and qid in leaves_data:
            image_name = None
            if taxa_data:
                # If the data file has an image for this taxon, use it
                image_name = get_image_from_taxa_data(taxa_data, leaves_data[qid]["taxon"])
            if not image_name and image:
                # Fall back to the image from the dump
                image_name = image["name"]
            if image_name and save_wiki_image(
                db, leaves_data[qid], image_name, src_flags["wiki"], qid, default_wiki_image_rating, output_dir, cropper
            ):
                leaves_that_got_images.add(qid)
        if vernaculars and qid in leaves_without_vn:
            save_wiki_vernaculars_for_qid(db, leaves_without_vn[qid], qid, vernaculars)

    # Log the leaves for which we couldn't find images
    info = ""
    for qid, _ in leaves_data.items():
        if qid not in leaves_that_got_images:
            info += f"\n  ott={leaves_data[qid]['ott']} qid={qid} {leaves_data[qid]['taxon']}"
    if len(info) != 0:
        logger.info(f"Taxa for which we couldn't find a proper image:{info}")


def process_args(args):
    outdir = args.output_dir
    config = read_config(args.conf_file)
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
    if not os.path.exists(outdir):
        logger.error(f"Output directory '{outdir}' does not exist")
        return

    db = connect_to_database(database)
    cropper = AzureImageCropper(config)

    taxa_data = {}
    if args.taxa_data_file:
        with open(args.taxa_data_file) as f:
            taxa_data = json.load(f)

    if args.subcommand == "leaf":
        # Process one leaf at a time
        if len(args.ott_or_taxa) > 1 and args.image is not None:
            raise ValueError("Cannot specify multiple taxa when using a bespoke image")
        for name in args.ott_or_taxa:
            process_leaf(db, name, args.image, args.rating, args.skip_images, outdir, cropper)
    elif args.subcommand == "clade":
        # Process all the taxa in the passed in clades
        for name in args.ott_or_taxa:
            process_clade(db, name, args.wd_dump, taxa_data, args.skip_images, outdir, cropper)


def setup_logging(args):
    log_level = "WARN"
    if args.quiet > 0:
        log_level = "ERROR"
        if args.quiet > 1:
            log_level = "CRITICAL"
            if args.quiet > 2:
                log_level = logging.CRITICAL + 1
    else:
        if args.verbosity > 0:
            log_level = "INFO"
        if args.verbosity > 1:
            log_level = "DEBUG"
    logging.basicConfig(level=log_level)
    return log_level


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])

    subparsers = parser.add_subparsers(help="help for subcommand", dest="subcommand")

    def add_common_args(parser):
        parser.add_argument(
            "-v",
            "--verbosity",
            action="count",
            default=0,
            help="How much information to print: use multiple times for more info",
        )
        parser.add_argument(
            "-q",
            "--quiet",
            action="count",
            default=0,
            help="Do not log warnings (-q) or errors (-qq)",
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Only process vernaculars, not images",
        )
        parser.add_argument(
            "--taxa-data-file",
            default=None,
            help="JSON file with persisted data about various taxa",
        )
        parser.add_argument(
            "-o",
            "--output-dir",
            default=None,
            help=(
                "The location to save the image files (e.g. 'FinalOutputs/img'). "
                "Defaults to ../../../static/FinalOutputs/img (relative to the script "
                "location). Files are saved to output_dir/{src_flag}/{3-digits}/fn.jpg"
            ),
        )
        parser.add_argument(
            "-c",
            "--conf-file",
            default=None,
            help=("The configuration file to use. " "Defaults to ../../../OZtree/private/appconfig.ini"),
        )

    parser_leaf = subparsers.add_parser("leaf", help="Process a single ott")
    parser_leaf.add_argument("ott_or_taxa", nargs="+", type=str, help="The leaf otts or taxa to process")
    parser_leaf.add_argument(
        "-i",
        "--image",
        type=str,
        help=(
            "A name of an image on wikimedia commons to use: if provided, you can give "
            "only one ott_or_taxon, and it will be treated as from a bespoke image src."
        ),
    )
    parser_leaf.add_argument(
        "-r",
        "--rating",
        type=int,
        help="The rating for the image (defaults to 40000)",
    )
    add_common_args(parser_leaf)

    parser_clade = subparsers.add_parser("clade", help="Process a full clade")
    parser_clade.add_argument(
        "wd_dump",
        type=str,
        help="The wikidata JSON dump file from which to get image URLs and vernaculars",
    )
    parser_clade.add_argument(
        "ott_or_taxa",
        nargs="+",
        type=str,
        help="The ott or taxa of the root of the clade(s)",
    )
    add_common_args(parser_clade)

    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        sys.exit()

    setup_logging(args)
    process_args(args)


if __name__ == "__main__":
    main()
