"""
This utility retrieves images from Wikidata for a given set of taxa or tips in a
clade. Either install the entire oz_tree_build package using
`python -m pip install oz_tree_build` or call the script directly as
`python -m oz_tree_build.images.get_wiki_images ...`. Images are
cropped to a 300x300 square using the Microsoft Azure Vision API, or
centered if no cropper is available.

The script can be used in two ways:
- To process a single taxon, use the 'leaf' subcommand. This will get the image
  for the given taxon, specified by OTT (e.g. 563151) or scientific name
  ('name') in the ordered_leaves or ordered_nodes tables e.g.
    * get_wiki_images.py leaf 563151
    * get_wiki_images.py leaf "Panthera leo" "File:Panthera leo.jpg"
    * get_wiki_images.py leaf "Panthera leo" "File:Panthera leo.jpg" 42000
  If no image is specified, a default one will be picked from the P18 field of the
  wikidata entry (e.g. see https://www.wikidata.org/wiki/Q140#P18), the image will
  be given a src of `src_flags["wiki"]` (20) and a src_id of the Wikimedia Commons
  page id of that image (not the taxon QID, since a taxon may have any number of
  images), and the rating will default to 35000 (of a maximum of 50000).
  Alternatively, if an image name is passed in, it will be treated as a bespoke image,
  given a src of `src_flags["onezoom_bespoke"]` (2) and the next available src_id
  (src_ids will therefore be incremented for each bespoke image processed), and a default
  rating of 40000.

- To process a full clade, use the 'clade' subcommand. This will get the images
  for all the taxa in the clade. A wikidata JSON dump file is required
  to find appropriate images for all the taxa: ideally this should be a filtered one
  such as OneZoom_latest-all.json. For example, to get images for all Panthera:
    * get_wiki_images.py clade OneZoom_latest-all.json 563151   # or
    * get_wiki_images.py clade OneZoom_latest-all.json "Panthera"
"""

import argparse
import datetime
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from PIL import Image

from .._OZglobals import src_flags
from ..user_agent import USER_AGENT_HEADERS
from ..utilities.cli_utils import add_common_args, setup_logging
from ..utilities.db_helper import (
    connect_to_database,
    default_appconfig,
    get_next_src_id_for_src,
    placeholder,
    read_config,
    resolve_clade_bounds,
)
from ..utilities.http_utils import make_http_request_with_retries
from ..utilities.wikidata_utils import (
    enumerate_wiki_dump_items,
    get_prop_from_taxa_data,
    get_qid_from_taxa_data,
    get_wikidata_json_for_qid,
    resolve_leaf,
)
from . import process_image_bits
from .image_cropping import AzureImageCropper, CenterImageCropper

default_wiki_image_rating = 35000
bespoke_wiki_image_rating = 40000

logger = logging.getLogger(Path(__file__).name)

default_outdir = os.path.join(
    os.pardir,
    os.pardir,
    os.pardir,
    "OZtree",
    "static",
    "FinalOutputs",
    "img",
)


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
                "preferred": 1 if claim.get("rank") == "preferred" else 0,
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


def get_image_license_info(escaped_image_name):
    """
    Use the Wikimedia API to get the license, artist, and Commons page id for a
    Wikimedia image.
    """

    image_metadata_url = (
        "https://commons.wikimedia.org/w/api.php"
        f"?action=query&titles=File%3a{escaped_image_name}&format=json&prop=imageinfo"
        "&iiprop=extmetadata&iiextmetadatafilter=License|LicenseShortName|LicenseUrl|Artist"
    )
    r = make_http_request_with_retries(image_metadata_url, headers=USER_AGENT_HEADERS)
    pages = r.json().get("query", {}).get("pages", {})
    extmetadata = None
    page_id = None
    for page in pages.values():
        if page.get("missing") or "imageinfo" not in page:
            continue
        extmetadata = page["imageinfo"][0].get("extmetadata")
        page_id = page.get("pageid")
        break
    if not extmetadata:
        logger.warning(f"Unknown image '{escaped_image_name}'")
        return None

    license_info = {"page_id": page_id}

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
        elif license_info["license_url"] == "http://artlibre.org/licence/lal/en":
            # See https://en.wikipedia.org/wiki/Free_Art_License
            license_info["license"] = "cc-by-sa-4.0"
        elif "License" in extmetadata:
            license_info["license"] = extmetadata["License"]["value"]
        else:
            # Some images have a LicenseShortName but not a License field
            license_info["license"] = extmetadata["LicenseShortName"]["value"]

        # If the license doesn't match what we deem acceptable, we can't use the image
        li = license_info["license"].lower()
        if (
            not li.startswith("cc")
            and not li.startswith("pd")
            and li not in ["flickr_commons", "copyrighted free use", "gfdl 1.2", "attribution", "no restrictions"]
        ):
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

    r = make_http_request_with_retries(image_location_url, headers=USER_AGENT_HEADERS)

    image_location_info = r.json()
    # Note that 'preferred' here refers to the preferred image *size*
    # not the preferred image itself
    image_url = image_location_info["preferred"]["url"]

    return image_url


def save_wiki_image(db, leaf_data, image_name, src, rating, output_dir, cropper, src_id=None):
    """
    Download a Wikimedia image and save it to the output directory. We keep both the
    uncropped and cropped versions of the image, along with the crop info.
    `src_id` determines the `src_id` to store in the database.
    When blank, uses the Commons page id of the image.
    `cropper` is an AzureImageCropper, or None to fall back to a centered crop.
    """

    wiki_image_url_prefix = "https://commons.wikimedia.org/wiki/File:"
    s = placeholder(db)

    ott = leaf_data["ott"]
    qid = leaf_data.get("qid")
    if not ott:
        qid_label = f"Q{qid}" if qid else "unknown taxon"
        logger.warning(f"No OTT for {qid_label}. Can't save {image_name}")
        return False

    # Wikimedia uses underscores instead of spaces in URLs
    escaped_image_name = image_name.replace(" ", "_").replace("&", "%26").replace("+", "%2B")
    # Also escape the ampersand and plus signs in the image name
    escaped_image_name = escaped_image_name.replace("&", "%26").replace("+", "%2B")

    license_info = get_image_license_info(escaped_image_name)
    if not license_info:
        logger.warning(f"Couldn't get license or artist for '{escaped_image_name}'. Ignoring it.")
        return False

    # When src_id is omitted, identify the image by its Commons page id.
    if src_id is None:
        page_id = license_info.get("page_id")
        src_id = int(page_id) if page_id else None
    if not src_id:
        logger.warning(f"No src_id for '{escaped_image_name}'. Ignoring it.")
        return False

    image_dir = os.path.normpath(os.path.join(output_dir, str(src), subdir_name(src_id)))
    image_path = f"{image_dir}/{src_id}.jpg"

    # If we already have an image for this taxon, and it's the same as the one
    # we're trying to download, skip it
    if leaf_data["img"]:
        assert leaf_data["img"].startswith(wiki_image_url_prefix)
        existing_image_name = leaf_data["img"][len(wiki_image_url_prefix) :]
        if existing_image_name == escaped_image_name:
            if os.path.isfile(image_path):
                logger.debug(f"Image '{image_name}' for {ott} is in the db, and at {image_path}")
                return True
            else:
                logger.warning(f"{image_name} for {ott} is in the db, but the " f"file is missing, so re-processing")

    logger.info(f"Processing image for ott={ott} (qid={qid}, page_id={src_id}): {image_name}")

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
        if license_string.startswith("cc-"):
            license_string = license_string.upper()
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
    response = make_http_request_with_retries(image_url, stream=True, headers=USER_AGENT_HEADERS)
    response.raise_for_status()

    with open(uncropped_image_path, "wb") as f:
        for chunk in response.iter_content(1024):
            f.write(chunk)

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
            datetime.datetime.now().isoformat(),
        ),
    )
    db.commit()

    # Since we added a new image, we need to update all the image bits for that ott
    process_image_bits.resolve(db, ott)

    return True


def get_image_from_taxa_data(taxa_data, taxon):
    return get_prop_from_taxa_data(taxa_data, taxon, "image")


def process_leaf(
    db,
    ott_or_taxon,
    image_name=None,
    taxa_data=None,
    rating=None,
    output_dir=None,
    cropper=None,
):
    """
    If ott_or_taxon is a number it's an ott, otherwise it's a taxon name. `cropper`
    is an AzureImageCropper, or None to fall back to a centered crop.
    """
    resolved = resolve_leaf(db, ott_or_taxon, taxa_data, logger)
    if resolved is None:
        return
    ott, qid, name = resolved

    # Three cases for the rating:
    # - If it's passed in, use it
    # - If it's not passed in for a bespoke image, use 40000
    # - for non-bespoke images, use 35000
    if rating is None:
        rating = bespoke_wiki_image_rating if image_name else default_wiki_image_rating

    json_item = get_wikidata_json_for_qid(qid)
    # If a specific image name is passed in (corresponding to a image name on
    # wikimedia commons), we use that. Otherwise, we need to look it up.
    # Also, if an image is passed in, we categorize it as a bespoke image, not wiki.
    if image_name:
        image = {"name": image_name}
        src = src_flags["onezoom_bespoke"]

        # Get the highest bespoke src_id, and add 1 to it for the new image src_id
        src_id = get_next_src_id_for_src(db, src)
    else:
        # If the data file has an image for this taxon, use it
        image_name = get_image_from_taxa_data(taxa_data, name)
        if image_name:
            image = {"name": image_name}
        else:
            image = get_preferred_or_first_image_from_json_item(json_item)
        src = src_flags["wiki"]
        src_id = None
    if image:
        leaf_data = {"ott": ott, "taxon": name, "img": None, "qid": qid}
        save_wiki_image(
            db=db,
            leaf_data=leaf_data,
            image_name=image["name"],
            src=src,
            rating=rating,
            output_dir=output_dir,
            cropper=cropper,
            src_id=src_id,
        )


def process_clade(db, ott_or_taxon, dump_file, taxa_data, output_dir, cropper=None):
    """
    `cropper` is an AzureImageCropper, or None to fall back to a centered crop.
    """
    s = placeholder(db)
    bounds = resolve_clade_bounds(db, ott_or_taxon, logger)
    if bounds is None:
        return
    (leaf_lft, leaf_rgt, _ott) = bounds

    # Get all leaves in the clade along with their wiki image, if any
    sql = f"""
    SELECT wikidata, ordered_leaves.ott, name, url FROM ordered_leaves
    LEFT OUTER JOIN (SELECT ott,src,url FROM images_by_ott
    WHERE src={s}) as wiki_images_by_ott ON ordered_leaves.ott=wiki_images_by_ott.ott
    WHERE ordered_leaves.id >= {s} AND ordered_leaves.id <= {s};
    """
    rows = db.executesql(sql, (src_flags["wiki"], leaf_lft, leaf_rgt))

    # If some rows don't have a qid, try to get that from the taxa data
    # If all else fails, skip that row.
    fixed_rows = []
    for row in rows:
        # Skip rows with no ott
        if row[1] is None:
            continue
        qid = row[0]
        if not qid:
            qid = get_qid_from_taxa_data(taxa_data, row[2])
            row = (qid, row[1], row[2], row[3])
        if not qid:
            logger.warning(f"No qid for {row[2]}. Skipping it.")
            continue
        fixed_rows.append(row)

    leaves_data = {qid: {"ott": ott, "taxon": name, "img": url, "qid": qid} for qid, ott, name, url in fixed_rows}
    total_to_process = len(leaves_data)
    logger.info(f"Found {total_to_process} leaves in the database")

    processed_count = 0
    start_time = time.time()
    leaves_that_got_images = set()
    for qid, image in enumerate_wiki_dump_items(dump_file, get_preferred_or_first_image_from_json_item):
        if qid in leaves_data:
            # If the data file has an image for this taxon, use it
            image_name = get_image_from_taxa_data(taxa_data, leaves_data[qid]["taxon"])
            if not image_name and image:
                # Fall back to the image from the dump
                image_name = image["name"]
            if image_name and save_wiki_image(
                db=db,
                leaf_data=leaves_data[qid],
                image_name=image_name,
                src=src_flags["wiki"],
                rating=default_wiki_image_rating,
                output_dir=output_dir,
                cropper=cropper,
            ):
                leaves_that_got_images.add(qid)
                logger.info(f"Saved image for ott={leaves_data[qid]['ott']} (qid={qid})")
            processed_count += 1
            elapsed = time.time() - start_time
            logger.info(f"Processed {processed_count} of {total_to_process} ({elapsed:.1f}s)")

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
        outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), default_outdir)
    if not os.path.exists(outdir):
        logger.error(f"Output directory '{outdir}' does not exist")
        return

    db = connect_to_database(database)

    cropper = None if args.no_azure_crop else AzureImageCropper(config)

    taxa_data = {}
    if args.taxa_data_file:
        with open(args.taxa_data_file) as f:
            taxa_data = json.load(f)

    if args.subcommand == "leaf":
        # Process one leaf at a time
        if len(args.ott_or_taxa) > 1 and args.image is not None:
            raise ValueError("Cannot specify multiple taxa when using a bespoke image")
        for name in args.ott_or_taxa:
            process_leaf(db, name, args.image, taxa_data, args.rating, outdir, cropper)
    elif args.subcommand == "clade":
        # Process all the taxa in the passed in clades
        for name in args.ott_or_taxa:
            process_clade(db, name, args.wd_dump, taxa_data, outdir, cropper)


def add_image_common_args(parser):
    add_common_args(parser)
    parser.add_argument(
        "--taxa-data-file",
        default=None,
        help="JSON file with persisted data about various taxa",
    )
    parser.add_argument(
        "-c",
        "--conf-file",
        default=None,
        help=(f"The configuration file to use. Defaults to {default_appconfig}"),
    )
    parser.add_argument(
        "--no-azure-crop",
        action="store_true",
        help=(
            "Do not use the Azure Vision API to crop images: instead, use a centered crop. "
            "Useful for testing or if you don't have an Azure Vision API key."
        ),
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help=(
            "The location to save the image files (e.g. 'FinalOutputs/img'). "
            f"Defaults to {default_outdir} (relative to the script "
            "location). Files are saved to output_dir/{src_flag}/{3-digits}/fn.jpg"
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])

    subparsers = parser.add_subparsers(help="help for subcommand", dest="subcommand")

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
    add_image_common_args(parser_leaf)

    parser_clade = subparsers.add_parser("clade", help="Process a full clade")
    parser_clade.add_argument(
        "wd_dump",
        type=str,
        help="The wikidata JSON dump file from which to get image URLs",
    )
    parser_clade.add_argument(
        "ott_or_taxa",
        nargs="+",
        type=str,
        help="The ott or taxa of the root of the clade(s)",
    )
    add_image_common_args(parser_clade)

    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        sys.exit()

    setup_logging(args)
    process_args(args)


if __name__ == "__main__":
    main()
