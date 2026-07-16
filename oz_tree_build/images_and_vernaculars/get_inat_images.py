"""
Harvest iNaturalist images for OneZoom leaves.

This module mirrors oz_tree_build.images_and_vernaculars.get_wiki_images, but
uses Wikidata property P3151 (iNaturalist taxon ID) to map OneZoom leaves onto
iNaturalist taxa, then retrieves open-licensed iNaturalist photos.

Only the following photo licences are accepted:
- CC0
- CC-BY
- CC-BY-SA

There are two image-selection routes:

1. API mode, best for prototypes and small clades. It asks the iNaturalist v2
   observations API for research-grade observations with photos, sorted by votes,
   then picks the first usable open-licensed photo. This is the only route that
   can approximate "most voted" because the open-data metadata dump does not
   include observation/photo vote totals.

2. Metadata mode, best for bulk work with the iNaturalist Open Data dump loaded
   into a local database. It joins observations, photos, and observers, filters to
   research-grade observations and the three allowed licences, then chooses the
   earliest-positioned / highest-resolution photo. This route scales, but cannot
   rank by votes because the metadata dump does not provide vote fields.

Usage examples:

    python -m oz_tree_build.images_and_vernaculars.get_inat_images leaf 563151 \
        --image-source api --no-azure-crop

    python -m oz_tree_build.images_and_vernaculars.get_inat_images clade \
        OneZoom_latest-all.json 563151 --image-source metadata \
        --inat-duckdb-path data/iNaturalist/inaturalist.duckdb

    python -m oz_tree_build.images_and_vernaculars.get_inat_images stats \
        --inat-duckdb-path data/iNaturalist/inaturalist.duckdb
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
from urllib.parse import urlparse

import duckdb
import requests
from PIL import Image

from .._OZglobals import src_flags
from ..utilities.db_helper import (
    connect_to_database,
    default_appconfig,
    placeholder,
    read_config,
)
from ..utilities.file_utils import enumerate_lines_from_file
from . import process_image_bits
from .get_wiki_images import default_outdir, get_qid_from_taxa_data, get_wikidata_json_for_qid, subdir_name
from .image_cropping import AzureImageCropper, CenterImageCropper

logger = logging.getLogger(Path(__file__).name)

# Keep this intentionally strict. Cropping/resizing is part of the pipeline, so
# no-derivatives licences are excluded, and non-commercial licences are excluded
# because OneZoom usage may not be strictly non-commercial in every context.
ALLOWED_INAT_PHOTO_LICENSES = frozenset({"cc0", "cc-by", "cc-by-sa"})
ALLOWED_INAT_PHOTO_LICENSES_SQL = tuple(sorted(ALLOWED_INAT_PHOTO_LICENSES))
# SQL predicate used against the iNaturalist metadata dump. Keep it aligned
# with normalise_inat_license()/is_allowed_inat_license(), but do the cheap
# filtering inside DuckDB so the full dump does not have to be loaded into
# Python. Non-commercial and no-derivatives variants are deliberately excluded.
INAT_USABLE_LICENSE_SQL = """
    normalized_license IN ('cc0', 'cc-by', 'cc-by-sa')
"""

INAT_SRC = src_flags["inat"]
DEFAULT_INAT_IMAGE_RATING = 34000
DEFAULT_API_PER_PAGE = 30
DEFAULT_IMAGE_SIZE = "medium"
INAT_API_OBSERVATIONS_URL = "https://api.inaturalist.org/v2/observations"
INAT_OPEN_DATA_PHOTO_PREFIX = "https://inaturalist-open-data.s3.amazonaws.com/photos"
INAT_OBSERVATION_PREFIX = "https://www.inaturalist.org/observations"
INAT_PHOTO_PREFIX = "https://www.inaturalist.org/photos"

inat_http_headers = {
    "User-Agent": "OneZoomBot/0.1 (https://www.onezoom.org/; mail@onezoom.org) get-inat-images/0.1"
}


class InatImageError(Exception):
    """Raised for recoverable iNaturalist image harvesting problems."""


def normalise_inat_license(license_code):
    """Return a normalized iNaturalist license code, e.g. 'cc-by-sa'."""
    if license_code is None:
        return None
    normalized = str(license_code).strip().lower().replace("_", "-")
    if normalized in {"cc0-1.0", "cc0 1.0", "public-domain", "pd"}:
        return "cc0"
    # iNaturalist metadata sometimes stores an upper-case code, and API values
    # sometimes include version suffixes. Keep only the family we explicitly allow.
    for allowed in sorted(ALLOWED_INAT_PHOTO_LICENSES, key=len, reverse=True):
        if normalized == allowed or normalized.startswith(allowed + "-"):
            return allowed
    return normalized


def is_allowed_inat_license(license_code):
    return normalise_inat_license(license_code) in ALLOWED_INAT_PHOTO_LICENSES


def inat_license_string(license_code):
    normalized = normalise_inat_license(license_code)
    return normalized.upper() if normalized else None


def inat_photo_url_from_open_data(photo_id, extension, size=DEFAULT_IMAGE_SIZE):
    """Build an S3 URL for an iNaturalist Open Data photo."""
    if not photo_id:
        raise ValueError("photo_id is required")
    if not extension:
        raise ValueError("extension is required")
    extension = str(extension).lower().lstrip(".")
    return f"{INAT_OPEN_DATA_PHOTO_PREFIX}/{photo_id}/{size}.{extension}"


def inat_photo_page_url(photo_id):
    return f"{INAT_PHOTO_PREFIX}/{photo_id}" if photo_id else None


def inat_observation_url(observation_uuid):
    return f"{INAT_OBSERVATION_PREFIX}/{observation_uuid}" if observation_uuid else None


def make_http_request_with_retries(url, *, params=None, stream=False):
    """Make an HTTP GET request with basic retry/backoff for rate limits."""
    retries = 6
    delay = 1
    for i in range(retries):
        r = requests.get(url, params=params, headers=inat_http_headers, stream=stream)
        if r.status_code == 200:
            return r
        if r.status_code in (429, 500, 502, 503, 504):
            logger.warning("HTTP %s on attempt %s for %s", r.status_code, i + 1, url)
            time.sleep(delay)
            delay *= 2
        else:
            raise InatImageError(f"Error requesting {url}: {r.status_code} {r.text}")
    raise InatImageError(f"Failed to get {url} after {retries} attempts")


def get_inat_taxon_id_from_json_item(json_item):
    """
    Extract Wikidata P3151 (iNaturalist taxon ID) from a Wikidata JSON item.

    Uses the preferred claim if present, otherwise the first normal claim.
    """
    claims = json_item.get("claims", {}).get("P3151", [])
    if not claims:
        return None
    preferred = [claim for claim in claims if claim.get("rank") == "preferred"]
    claim = preferred[0] if preferred else claims[0]
    try:
        value = claim["mainsnak"]["datavalue"]["value"]
    except (KeyError, TypeError):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning("Invalid P3151 value in Q%s: %r", json_item.get("id"), value)
        return None


def enumerate_wikidata_dump_items_with_inat_ids(wikidata_dump_file):
    """Yield (qid, inat_taxon_id) for dump items containing P3151."""
    for _, line in enumerate_lines_from_file(wikidata_dump_file):
        if not line.startswith('{"type":'):
            continue
        json_item = json.loads(line.rstrip().rstrip(","))
        inat_taxon_id = get_inat_taxon_id_from_json_item(json_item)
        if inat_taxon_id is None:
            continue
        qid = int(json_item["id"][1:])
        yield qid, inat_taxon_id


def get_inat_taxon_id_from_taxa_data(taxa_data, taxon):
    """Read an optional cached iNat taxon ID from a taxa-data JSON object."""
    if taxa_data is None or taxon not in taxa_data:
        return None
    data = taxa_data[taxon]
    if not data:
        return None
    if "redirect" in data:
        data = taxa_data[data["redirect"]]
    for prop in ("inat", "inat_taxon", "inat_taxon_id", "inaturalist", "inaturalist_taxon_id"):
        if prop in data and data[prop]:
            return int(data[prop])
    return None


def get_inat_taxon_id_for_qid(qid):
    json_item = get_wikidata_json_for_qid(qid)
    return get_inat_taxon_id_from_json_item(json_item)


def preferred_api_photo_url(photo, size=DEFAULT_IMAGE_SIZE):
    """Return a usable API photo URL, preferring medium/large URLs over square thumbnails."""
    # Some API responses expose explicit size keys.
    if size == "large" and photo.get("large_url"):
        return photo["large_url"]
    if size == "medium" and photo.get("medium_url"):
        return photo["medium_url"]
    for key in ("medium_url", "large_url", "url"):
        url = photo.get(key)
        if url:
            break
    else:
        return None

    # iNaturalist API photo URLs often end in /square.ext by default. Replace
    # the size segment with the requested size when possible.
    return re.sub(r"/(square|thumb|small|medium|large)\.([A-Za-z0-9]+)(\?.*)?$", f"/{size}.\\2", url)


def photo_id_from_api_photo(photo):
    return photo.get("id") or photo.get("photo_id")


def dimensions_from_api_photo(photo):
    dims = photo.get("original_dimensions") or photo.get("dimensions") or {}
    return int(dims.get("width") or photo.get("width") or 0), int(dims.get("height") or photo.get("height") or 0)


def observer_name_from_api_observation(observation):
    user = observation.get("user") or {}
    return user.get("name") or user.get("login") or "Unknown iNaturalist observer"


def attribution_for_inat_photo(license_code, observer_name):
    license_string = inat_license_string(license_code)
    observer_name = observer_name or "Unknown iNaturalist observer"
    if normalise_inat_license(license_code) == "cc0":
        return f"{observer_name}, no rights reserved ({license_string})"
    return f"© {observer_name}, some rights reserved ({license_string})"


def candidate_from_api_observation(observation, photo, position=0, image_size=DEFAULT_IMAGE_SIZE):
    license_code = normalise_inat_license(photo.get("license_code") or photo.get("license"))
    if license_code not in ALLOWED_INAT_PHOTO_LICENSES:
        return None

    photo_id = photo_id_from_api_photo(photo)
    image_url = preferred_api_photo_url(photo, image_size)
    if not image_url:
        return None

    width, height = dimensions_from_api_photo(photo)
    observer_name = photo.get("attribution_name") or observer_name_from_api_observation(observation)
    observation_uuid = observation.get("uuid") or observation.get("observation_uuid")
    observation_url = observation.get("uri") or inat_observation_url(observation_uuid) or observation.get("url")
    page_url = photo.get("native_page_url") or inat_photo_page_url(photo_id) or observation_url

    votes = observation.get("cached_votes_total") or observation.get("votes_count") or observation.get("votes") or 0
    try:
        votes = int(votes)
    except (TypeError, ValueError):
        votes = 0

    return {
        "photo_id": int(photo_id) if photo_id is not None else None,
        "src_id": int(photo_id) if photo_id is not None else None,
        "image_url": image_url,
        "page_url": page_url,
        "observation_url": observation_url,
        "observation_uuid": observation_uuid,
        "license": license_code,
        "license_string": inat_license_string(license_code),
        "rights": attribution_for_inat_photo(license_code, observer_name),
        "observer_name": observer_name,
        "width": width,
        "height": height,
        "position": position,
        "votes": votes,
        "quality_grade": observation.get("quality_grade"),
        "verified": str(observation.get("quality_grade", "")).lower() in {"research", "research grade"},
        "source": "api",
    }


def score_candidate(candidate):
    """Score candidates deterministically; API results are already vote-ordered."""
    if not candidate:
        return -1
    score = 0
    score += int(candidate.get("votes") or 0) * 1_000_000
    if str(candidate.get("quality_grade", "")).lower() in {"research", "research grade"}:
        score += 100_000
    if candidate.get("license") == "cc0":
        score += 3_000
    elif candidate.get("license") == "cc-by":
        score += 2_000
    elif candidate.get("license") == "cc-by-sa":
        score += 1_000
    position = candidate.get("position")
    if position is None:
        position = 999
    score -= int(position) * 100
    score += min(int(candidate.get("width") or 0) * int(candidate.get("height") or 0), 20_000_000) // 10_000
    return score


def get_best_photo_from_inat_api(inat_taxon_id, *, per_page=DEFAULT_API_PER_PAGE, image_size=DEFAULT_IMAGE_SIZE):
    """
    Query iNaturalist v2 observations and choose the best allowed photo.

    This uses order_by=votes because the open-data metadata dump does not expose
    vote totals. Only CC0, CC-BY, and CC-BY-SA photo licences are requested and
    accepted.
    """
    params = {
        "taxon_id": str(inat_taxon_id),
        "photos": "true",
        "quality_grade": "research",
        "photo_license": ",".join(sorted(ALLOWED_INAT_PHOTO_LICENSES)),
        "order_by": "votes",
        "order": "desc",
        "per_page": str(per_page),
        # Keep fields broad because iNat v2 nested-field syntax can change. The
        # selector functions above are defensive and ignore missing fields.
        "fields": "all",
    }
    response = make_http_request_with_retries(INAT_API_OBSERVATIONS_URL, params=params)
    data = response.json()
    candidates = []
    for observation in data.get("results", []):
        for position, photo in enumerate(observation.get("photos") or []):
            candidate = candidate_from_api_observation(observation, photo, position, image_size=image_size)
            if candidate:
                candidates.append(candidate)
    if not candidates:
        return None
    return max(candidates, key=score_candidate)


def connect_to_metadata_database(metadata_db_path):
    """Connect to the local iNaturalist DuckDB metadata database."""
    if not metadata_db_path:
        raise ValueError("--inat-duckdb-path is required for --image-source metadata and stats")
    return duckdb.connect(str(metadata_db_path), read_only=True)


def get_inat_metadata_db_path(config, args):
    if args.inat_duckdb_path:
        return args.inat_duckdb_path
    if config.has_section("inat"):
        for key in ("duckdb_path", "metadata_duckdb_path", "metadata_db_path", "metadata_uri", "metadata_db_uri", "uri"):
            if config.has_option("inat", key):
                return config.get("inat", key)
    return None


def run_duckdb_query(inat_db, sql, params=None):
    return inat_db.execute(sql, params or ()).fetchall()


def rows_to_dicts(columns, rows):
    return [dict(zip(columns, row)) for row in rows]


def get_best_photo_from_metadata_db(inat_db, inat_taxon_id, *, image_size=DEFAULT_IMAGE_SIZE):
    """
    Query a local iNaturalist Open Data metadata database for the best photo.

    The metadata dump has no vote columns, so this is not a "most voted" ranking.
    It is the scalable fallback: research-grade, allowed licence, first photo
    position, then largest image.
    """
    columns = [
        "photo_id",
        "extension",
        "license",
        "width",
        "height",
        "position",
        "observation_uuid",
        "quality_grade",
        "observed_on",
        "observer_login",
        "observer_name",
    ]
    sql = f"""
    WITH candidate_photos AS (
        SELECT
            p.photo_id,
            p.extension,
            p.license,
            LOWER(REPLACE(COALESCE(p.license, ''), '_', '-')) AS normalized_license,
            p.width,
            p.height,
            p.position,
            obs.observation_uuid,
            obs.quality_grade,
            obs.observed_on,
            o.login AS observer_login,
            o.name AS observer_name
        FROM observations obs
        JOIN photos p ON obs.observation_uuid = p.observation_uuid
        LEFT JOIN observers o ON p.observer_id = o.observer_id
        WHERE obs.taxon_id = ?
          AND LOWER(obs.quality_grade) IN ('research', 'research grade')
          AND p.photo_id IS NOT NULL
          AND p.extension IS NOT NULL
    )
    SELECT
        photo_id,
        extension,
        license,
        width,
        height,
        position,
        observation_uuid,
        quality_grade,
        observed_on,
        observer_login,
        observer_name
    FROM candidate_photos
    WHERE {INAT_USABLE_LICENSE_SQL}
    ORDER BY
      COALESCE(position, 9999) ASC,
      (COALESCE(width, 0) * COALESCE(height, 0)) DESC,
      photo_id ASC
    LIMIT 1;
    """
    rows = rows_to_dicts(columns, run_duckdb_query(inat_db, sql, (inat_taxon_id,)))
    if not rows:
        return None
    row = rows[0]
    license_code = normalise_inat_license(row["license"])
    if license_code not in ALLOWED_INAT_PHOTO_LICENSES:
        return None
    observer_name = row.get("observer_name") or row.get("observer_login") or "Unknown iNaturalist observer"
    photo_id = row["photo_id"]
    observation_uuid = str(row["observation_uuid"]) if row.get("observation_uuid") else None
    return {
        "photo_id": int(photo_id),
        "src_id": int(photo_id),
        "image_url": inat_photo_url_from_open_data(photo_id, row["extension"], image_size),
        "page_url": inat_photo_page_url(photo_id),
        "observation_url": inat_observation_url(observation_uuid),
        "observation_uuid": observation_uuid,
        "license": license_code,
        "license_string": inat_license_string(license_code),
        "rights": attribution_for_inat_photo(license_code, observer_name),
        "observer_name": observer_name,
        "width": int(row.get("width") or 0),
        "height": int(row.get("height") or 0),
        "position": int(row.get("position") or 0),
        "votes": None,
        "quality_grade": row.get("quality_grade"),
        "verified": True,
        "source": "metadata",
    }


def get_best_photo(inat_taxon_id, *, image_source, inat_db=None, per_page=DEFAULT_API_PER_PAGE, image_size=DEFAULT_IMAGE_SIZE):
    if image_source == "api":
        return get_best_photo_from_inat_api(inat_taxon_id, per_page=per_page, image_size=image_size)
    if image_source == "metadata":
        if inat_db is None:
            raise ValueError("inat_db must be provided for metadata image source")
        return get_best_photo_from_metadata_db(inat_db, inat_taxon_id, image_size=image_size)
    raise ValueError(f"Unknown image_source: {image_source}")


def get_usable_photo_species_stats(inat_db):
    """Return counts of iNaturalist species that have at least one usable photo."""
    columns = [
        "inat_species",
        "inat_species_with_usable_photos",
        "inat_species_with_research_grade_usable_photos",
    ]
    sql = f"""
    WITH photo_observations AS (
        SELECT
            obs.taxon_id,
            obs.quality_grade,
            LOWER(REPLACE(COALESCE(p.license, ''), '_', '-')) AS normalized_license
        FROM observations obs
        JOIN photos p ON obs.observation_uuid = p.observation_uuid
        WHERE p.photo_id IS NOT NULL
    ),
    species_taxa AS (
        SELECT taxon_id
        FROM taxa
        WHERE LOWER(rank) = 'species'
    ),
    usable_species AS (
        SELECT DISTINCT po.taxon_id
        FROM photo_observations po
        JOIN species_taxa st ON po.taxon_id = st.taxon_id
        WHERE {INAT_USABLE_LICENSE_SQL}
    ),
    usable_research_grade_species AS (
        SELECT DISTINCT po.taxon_id
        FROM photo_observations po
        JOIN species_taxa st ON po.taxon_id = st.taxon_id
        WHERE {INAT_USABLE_LICENSE_SQL}
          AND LOWER(po.quality_grade) IN ('research', 'research grade')
    )
    SELECT
        (SELECT COUNT(*) FROM species_taxa) AS inat_species,
        (SELECT COUNT(*) FROM usable_species) AS inat_species_with_usable_photos,
        (SELECT COUNT(*) FROM usable_research_grade_species) AS inat_species_with_research_grade_usable_photos;
    """
    rows = rows_to_dicts(columns, run_duckdb_query(inat_db, sql))
    return rows[0] if rows else dict.fromkeys(columns, 0)


def print_usable_photo_species_stats(inat_db):
    stats = get_usable_photo_species_stats(inat_db)
    print(f"iNaturalist species: {stats['inat_species']:,}")
    print(f"iNaturalist species with >=1 usable photo: {stats['inat_species_with_usable_photos']:,}")
    print(
        "iNaturalist species with >=1 usable research-grade photo: "
        f"{stats['inat_species_with_research_grade_usable_photos']:,}"
    )


def safe_src_id(candidate):
    src_id = candidate.get("src_id") or candidate.get("photo_id")
    if src_id is None:
        # API responses should include an ID; this is only a fallback to keep the
        # file-system/database logic from receiving None.
        parsed = urlparse(candidate.get("image_url") or "")
        match = re.search(r"/photos/(\d+)/", parsed.path)
        if match:
            src_id = int(match.group(1))
    if src_id is None:
        raise InatImageError("Cannot save iNaturalist image without a photo_id/src_id")
    return int(src_id)


def save_inat_image(db, leaf_data, candidate, rating, output_dir, cropper):
    """
    Download, crop, save, and insert an iNaturalist image into images_by_ott.
    """
    s = placeholder(db)
    ott = leaf_data["ott"]
    if not ott:
        logger.warning("No OTT for iNaturalist photo %s. Can't save image", candidate.get("photo_id"))
        return False

    if not is_allowed_inat_license(candidate.get("license")):
        logger.warning("Rejecting iNaturalist photo %s because of license %r", candidate.get("photo_id"), candidate.get("license"))
        return False

    src = INAT_SRC
    src_id = safe_src_id(candidate)
    page_url = candidate.get("page_url") or candidate.get("observation_url") or inat_photo_page_url(src_id)
    image_url = candidate.get("image_url")
    if not image_url:
        logger.warning("No downloadable image URL for iNaturalist photo %s", src_id)
        return False

    image_dir = os.path.normpath(os.path.join(output_dir, str(src), subdir_name(src_id)))
    image_path = f"{image_dir}/{src_id}.jpg"

    if leaf_data.get("img") == page_url and os.path.isfile(image_path):
        logger.debug("iNaturalist image %s for ott=%s is already present", src_id, ott)
        return True

    logger.info("Processing iNaturalist image for ott=%s, taxon=%s, photo_id=%s", ott, leaf_data.get("taxon"), src_id)

    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    uncropped_image_path = f"{image_dir}/{src_id}_uncropped.jpg"
    response = make_http_request_with_retries(image_url, stream=True)
    with open(uncropped_image_path, "wb") as f:
        for chunk in response.iter_content(1024):
            if chunk:
                f.write(chunk)

    if cropper is None:
        cropper = CenterImageCropper()

    crop_box = cropper.crop(image_url, uncropped_image_path)

    im = Image.open(uncropped_image_path)
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
        logger.warning("Error saving %s: %s", image_path, e)
        return False

    crop_info_path = f"{image_dir}/{src_id}_cropinfo.txt"
    with open(crop_info_path, "w") as f:
        f.write(f"{crop_box.x},{crop_box.y},{crop_box.width},{crop_box.height}")

    # Keep one iNaturalist image per OTT for this source.
    db.executesql(f"DELETE FROM images_by_ott WHERE ott={s} and src={s};", (ott, src))

    is_public_domain = normalise_inat_license(candidate.get("license")) == "cc0"
    verified = 1 if candidate.get("verified") else 0

    db.executesql(
        "INSERT INTO images_by_ott "
        "(ott,src,src_id,url,rating,rating_confidence,best_any,best_verified,best_pd,"
        "overall_best_any,overall_best_verified,overall_best_pd,rights,licence,updated) "
        f"VALUES ({s},{s},{s},{s},{s},{s},{s},{s},{s},{s},{s},{s},{s},{s},{s});",
        (
            ott,
            src,
            src_id,
            page_url,
            rating,
            None,
            1,
            verified,
            (1 if is_public_domain else 0),
            1,
            verified,
            (1 if is_public_domain else 0),
            candidate.get("rights"),
            candidate.get("license_string") or inat_license_string(candidate.get("license")),
            datetime.datetime.now().isoformat(),
        ),
    )
    db.commit()

    process_image_bits.resolve(db, ott)
    logger.info("Saved iNaturalist photo %s for ott=%s in %s", src_id, ott, image_path)
    return True


def get_leaf_record(db, ott_or_taxon):
    s = placeholder(db)
    sql = "SELECT ott,wikidata,name FROM ordered_leaves WHERE "
    if ott_or_taxon.lstrip("-").isnumeric():
        ott_or_taxon_type = "ott"
        sql += f"ott={s};"
    else:
        ott_or_taxon_type = "name"
        sql += f"name={s};"

    result = db.executesql(sql, (ott_or_taxon,))
    if len(result) > 1:
        logger.error("Multiple results for '%s'", ott_or_taxon)
        return None
    if len(result) == 0:
        logger.error("%s '%s' not found in ordered_leaves table", ott_or_taxon_type, ott_or_taxon)
        return None
    ott, qid, name = result[0]
    return {"ott": ott, "qid": qid, "taxon": name, "img": None}


def process_leaf(
    db,
    ott_or_taxon,
    taxa_data=None,
    rating=None,
    output_dir=None,
    cropper=None,
    image_source="api",
    inat_db=None,
    per_page=DEFAULT_API_PER_PAGE,
    image_size=DEFAULT_IMAGE_SIZE,
    inat_taxon_id=None,
):
    leaf_data = get_leaf_record(db, ott_or_taxon)
    if leaf_data is None:
        return False

    qid = leaf_data["qid"] or get_qid_from_taxa_data(taxa_data, leaf_data["taxon"])
    inat_taxon_id = inat_taxon_id or get_inat_taxon_id_from_taxa_data(taxa_data, leaf_data["taxon"])
    if not inat_taxon_id:
        if not qid:
            logger.warning("No Wikidata QID or iNaturalist taxon ID for %s. Skipping.", leaf_data["taxon"])
            return False
        inat_taxon_id = get_inat_taxon_id_for_qid(qid)
    if not inat_taxon_id:
        logger.warning("No Wikidata P3151/iNaturalist taxon ID for %s. Skipping.", leaf_data["taxon"])
        return False

    if rating is None:
        rating = DEFAULT_INAT_IMAGE_RATING

    candidate = get_best_photo(
        inat_taxon_id,
        image_source=image_source,
        inat_db=inat_db,
        per_page=per_page,
        image_size=image_size,
    )
    if not candidate:
        logger.warning("No allowed iNaturalist image found for %s (iNat taxon %s)", leaf_data["taxon"], inat_taxon_id)
        return False

    return save_inat_image(db, leaf_data, candidate, rating, output_dir, cropper)


def process_clade(
    db,
    ott_or_taxon,
    dump_file,
    taxa_data=None,
    rating=None,
    output_dir=None,
    cropper=None,
    image_source="metadata",
    inat_db=None,
    per_page=DEFAULT_API_PER_PAGE,
    image_size=DEFAULT_IMAGE_SIZE,
):
    s = placeholder(db)
    sql = "SELECT leaf_lft,leaf_rgt,ott FROM ordered_nodes WHERE "
    if ott_or_taxon.isnumeric():
        sql += f"ott={s};"
    else:
        sql += f"name={s};"
    rows = db.executesql(sql, (ott_or_taxon,))
    if len(rows) == 0:
        raise ValueError(f"'{ott_or_taxon}' not found in ordered_nodes table")
    if len(rows) > 1:
        logger.error("Multiple results for '%s', choose out of these OTTs: %s", ott_or_taxon, [r[2] for r in rows])
        return
    leaf_lft, leaf_rgt, _ = rows[0]

    sql = f"""
    SELECT wikidata, ordered_leaves.ott, name, url FROM ordered_leaves
    LEFT OUTER JOIN (SELECT ott,src,url FROM images_by_ott
    WHERE src={s}) as inat_images_by_ott ON ordered_leaves.ott=inat_images_by_ott.ott
    WHERE ordered_leaves.id >= {s} AND ordered_leaves.id <= {s};
    """
    rows = db.executesql(sql, (INAT_SRC, leaf_lft, leaf_rgt))

    leaves_data = {}
    for qid, ott, name, url in rows:
        if ott is None:
            continue
        if not qid:
            qid = get_qid_from_taxa_data(taxa_data, name)
        if not qid:
            logger.warning("No qid for %s. Skipping it.", name)
            continue
        leaves_data[qid] = {"ott": ott, "taxon": name, "img": url}
    logger.info("Found %s leaves in the database", len(leaves_data))

    if rating is None:
        rating = DEFAULT_INAT_IMAGE_RATING

    leaves_that_got_images = set()
    for qid, inat_taxon_id in enumerate_wikidata_dump_items_with_inat_ids(dump_file):
        if qid not in leaves_data:
            continue
        candidate = get_best_photo(
            inat_taxon_id,
            image_source=image_source,
            inat_db=inat_db,
            per_page=per_page,
            image_size=image_size,
        )
        if candidate and save_inat_image(db, leaves_data[qid], candidate, rating, output_dir, cropper):
            leaves_that_got_images.add(qid)

    missing = ""
    for qid, leaf_data in leaves_data.items():
        if qid not in leaves_that_got_images:
            missing += f"\n  ott={leaf_data['ott']} qid={qid} {leaf_data['taxon']}"
    if missing:
        logger.info("Taxa for which we couldn't find an allowed iNaturalist image:%s", missing)


def process_args(args):
    config = read_config(args.conf_file)

    if args.subcommand == "stats":
        inat_db_path = get_inat_metadata_db_path(config, args)
        inat_db = connect_to_metadata_database(inat_db_path)
        try:
            print_usable_photo_species_stats(inat_db)
        finally:
            inat_db.close()
        return

    outdir = args.output_dir
    database = config.get("db", "uri")

    if outdir is None:
        outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), default_outdir)
    if not os.path.exists(outdir):
        logger.error("Output directory '%s' does not exist", outdir)
        return

    db = connect_to_database(database)
    cropper = None if args.no_azure_crop else AzureImageCropper(config)

    inat_db = None
    if args.image_source == "metadata":
        inat_db_path = get_inat_metadata_db_path(config, args)
        inat_db = connect_to_metadata_database(inat_db_path)

    taxa_data = {}
    if args.taxa_data_file:
        with open(args.taxa_data_file) as f:
            taxa_data = json.load(f)

    if args.subcommand == "leaf":
        if len(args.ott_or_taxa) > 1 and args.inat_taxon_id is not None:
            raise ValueError("Cannot specify --inat-taxon-id when processing multiple taxa")
        for name in args.ott_or_taxa:
            process_leaf(
                db,
                name,
                taxa_data=taxa_data,
                rating=args.rating,
                output_dir=outdir,
                cropper=cropper,
                image_source=args.image_source,
                inat_db=inat_db,
                per_page=args.api_per_page,
                image_size=args.image_size,
                inat_taxon_id=args.inat_taxon_id,
            )
    elif args.subcommand == "clade":
        for name in args.ott_or_taxa:
            process_clade(
                db,
                name,
                args.wd_dump,
                taxa_data=taxa_data,
                rating=args.rating,
                output_dir=outdir,
                cropper=cropper,
                image_source=args.image_source,
                inat_db=inat_db,
                per_page=args.api_per_page,
                image_size=args.image_size,
            )

    if inat_db is not None:
        inat_db.close()
    db.close()


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

    def add_common_args(subparser):
        subparser.add_argument("-v", "--verbosity", action="count", default=0)
        subparser.add_argument("-q", "--quiet", action="count", default=0)
        subparser.add_argument("--taxa-data-file", default=None, help="JSON file with persisted data about various taxa")
        subparser.add_argument(
            "--no-azure-crop",
            action="store_true",
            help="Do not use the Azure Vision API to crop images; use a centered crop instead.",
        )
        subparser.add_argument(
            "-o",
            "--output-dir",
            default=None,
            help=(
                "The location to save image files (e.g. FinalOutputs/img). "
                "Files are saved to output_dir/{src_flag}/{last-three-digits}/{photo_id}.jpg"
            ),
        )
        subparser.add_argument("-c", "--conf-file", default=None, help=f"The configuration file. Defaults to {default_appconfig}")
        subparser.add_argument(
            "--image-source",
            choices=("api", "metadata"),
            default="api",
            help=(
                "api = use iNaturalist API ordered by votes; metadata = use local Open Data metadata DB. "
                "Metadata mode cannot rank by votes because the dump does not include vote counts."
            ),

        subparser.add_argument(
            "--inat-duckdb-path",
            "--inat-db-uri",
            dest="inat_duckdb_path",
            default=None,
            help="Path to local iNaturalist DuckDB metadata DB, e.g. data/iNaturalist/inaturalist.duckdb",
        )
        subparser.add_argument("--api-per-page", type=int, default=DEFAULT_API_PER_PAGE)
        subparser.add_argument("--image-size", choices=("medium", "large"), default=DEFAULT_IMAGE_SIZE)
        subparser.add_argument("-r", "--rating", type=int, help=f"Image rating; defaults to {DEFAULT_INAT_IMAGE_RATING}")

    parser_leaf = subparsers.add_parser("leaf", help="Process one or more leaves")
    parser_leaf.add_argument("ott_or_taxa", nargs="+", type=str, help="Leaf OTTs or names to process")
    parser_leaf.add_argument("--inat-taxon-id", type=int, default=None, help="Manual iNaturalist taxon ID override for one leaf")
    add_common_args(parser_leaf)

    parser_clade = subparsers.add_parser("clade", help="Process a full clade")
    parser_clade.add_argument("wd_dump", type=str, help="Filtered Wikidata JSON dump containing P3151 claims")
    parser_clade.add_argument("ott_or_taxa", nargs="+", type=str, help="Root node OTT or name")
    add_common_args(parser_clade)

    parser_stats = subparsers.add_parser("stats", help="Print usable-photo species counts from the iNaturalist DuckDB metadata DB")
    parser_stats.add_argument("-v", "--verbosity", action="count", default=0)
    parser_stats.add_argument("-q", "--quiet", action="count", default=0)
    parser_stats.add_argument("-c", "--conf-file", default=None, help=f"The configuration file. Defaults to {default_appconfig}")
    parser_stats.add_argument(
        "--inat-duckdb-path",
        "--inat-db-uri",
        dest="inat_duckdb_path",
        default=None,
        help="Path to local iNaturalist DuckDB metadata DB, e.g. data/iNaturalist/inaturalist.duckdb",
    )

    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        sys.exit()

    setup_logging(args)
    process_args(args)


if __name__ == "__main__":
    main()
