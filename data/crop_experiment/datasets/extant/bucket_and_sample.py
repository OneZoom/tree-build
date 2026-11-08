"""
Run on beta.onezoom.org with /home/jared/tree-build/venv/bin/python.
Buckets all src=20 (wiki) images into 6 coarse clade groups via nested-set
containment, then within each bucket randomly samples images whose uncropped
original has aspect ratio (long/short side) >= RATIO_THRESHOLD, until each
bucket's quota is filled.
"""

import logging
import os
import random
import sys

sys.path.insert(0, "/home/jared/tree-build")

from PIL import Image

from oz_tree_build._OZglobals import src_flags
from oz_tree_build.images.get_wiki_images import subdir_name
from oz_tree_build.utilities.db_helper import connect_to_database, placeholder, resolve_clade_bounds

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bucket_and_sample")

CONF_FILE = "/home/web2py/beta.onezoom.org/applications/OZtree/private/appconfig.ini"
IMG_ROOT = "/home/web2py/beta.onezoom.org/applications/OZtree/static/FinalOutputs/img"
RATIO_THRESHOLD = 1.4
SEED = 42
TOTAL = 400

# Marker ott ids for the 6 coarse buckets (checked in this priority order;
# first match wins). "other" catches anything not in any of these.
MARKERS = [
    ("vertebrate", "801601"),  # Vertebrata (subphylum)
    ("arthropod", "632179"),  # Arthropoda (phylum)
    ("other_invertebrate", "691846"),  # Metazoa (kingdom) -- catches remaining animals
    ("plant", "5268475"),  # Archaeplastida (kingdom) -- land plants + algae
    ("fungus", "352914"),  # Fungi (kingdom)
]

db = connect_to_database(conf_file=CONF_FILE)
s = placeholder(db)

bounds = {}
for name, ott in MARKERS:
    leaf_lft, leaf_rgt, resolved_ott = resolve_clade_bounds(db, ott, logger)
    bounds[name] = (leaf_lft, leaf_rgt)
    logger.info(f"{name}: ott={resolved_ott} leaf_lft={leaf_lft} leaf_rgt={leaf_rgt}")

sql = f"""
SELECT images_by_ott.ott, images_by_ott.src_id, ordered_leaves.id, ordered_leaves.name
FROM images_by_ott
JOIN ordered_leaves ON images_by_ott.ott = ordered_leaves.ott
WHERE images_by_ott.src = {s}
"""
rows = db.executesql(sql, (src_flags["wiki"],))
logger.info(f"total src=20 rows with a resolvable leaf position: {len(rows)}")


def bucket_for(leaf_id):
    for name, _ott in MARKERS:
        lft, rgt = bounds[name]
        if lft <= leaf_id <= rgt:
            return name
    return "other"


buckets = {name: [] for name, _ in MARKERS}
buckets["other"] = []
missing_file = 0
for ott, src_id, leaf_id, taxon_name in rows:
    subdir = subdir_name(src_id)
    path = os.path.join(IMG_ROOT, "20", subdir, f"{src_id}_uncropped.jpg")
    if not os.path.isfile(path):
        missing_file += 1
        continue
    b = bucket_for(leaf_id)
    buckets[b].append((ott, taxon_name, src_id, path))

logger.info(f"rows with no uncropped file on disk: {missing_file}")
for name in list(buckets.keys()):
    logger.info(f"bucket '{name}': {len(buckets[name])} candidates")

# Even quota across the 6 buckets, remainder distributed to the first few
names = [n for n, _ in MARKERS] + ["other"]
base_quota = TOTAL // len(names)
remainder = TOTAL - base_quota * len(names)
quotas = {name: base_quota + (1 if i < remainder else 0) for i, name in enumerate(names)}
logger.info(f"quotas: {quotas}")

random.seed(SEED)
selected = []
shortfalls = {}
for name in names:
    candidates = buckets[name][:]
    random.shuffle(candidates)
    quota = quotas[name]
    picked = []
    checked = 0
    for ott, taxon_name, src_id, path in candidates:
        if len(picked) >= quota:
            break
        checked += 1
        try:
            with Image.open(path) as im:
                w, h = im.size
        except Exception as e:
            logger.warning(f"could not read {path}: {e}")
            continue
        long_side, short_side = max(w, h), min(w, h)
        if short_side == 0:
            continue
        ratio = long_side / short_side
        if ratio >= RATIO_THRESHOLD:
            picked.append((ott, taxon_name, src_id, path, w, h, ratio))
    logger.info(f"bucket '{name}': picked {len(picked)}/{quota} after checking {checked}/{len(candidates)} candidates")
    if len(picked) < quota:
        shortfalls[name] = quota - len(picked)
    selected.extend((name, *row) for row in picked)

logger.info(f"total selected: {len(selected)}")
if shortfalls:
    logger.warning(f"shortfalls (quota not met): {shortfalls}")

out_path = "/home/jared/crop_sample_selection.tsv"
with open(out_path, "w") as f:
    f.write("bucket\tott\tname\tsrc_id\tpath\twidth\theight\taspect_ratio\n")
    for bucket, ott, taxon_name, src_id, path, w, h, ratio in selected:
        f.write(f"{bucket}\t{ott}\t{taxon_name}\t{src_id}\t{path}\t{w}\t{h}\t{ratio:.3f}\n")

print("DONE_MARKER")
