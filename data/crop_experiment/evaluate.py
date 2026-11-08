"""
The image sets, and scoring predicted crops against the hand-labelled ideal crops.

Each image set is a directory in datasets/ with sample_selection.tsv, originals/ and
labels/. An image's key is "<set>/<src_id>", e.g. "extant/7721568".

Usage: python data/crop_experiment/evaluate.py PREDICTIONS

PREDICTIONS is a predictions.tsv (columns set, src_id, x, y, width, height, in pixels
of the uncropped image) or a run directory containing one. A missing prediction
scores an IoU of 0; images without a label aren't scored.
"""

import argparse
import csv
import re
from functools import cache
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
SETS = {name: EXPERIMENT_DIR / "datasets" / name for name in ("extant", "extinct")}
RUNS_DIR = EXPERIMENT_DIR / "runs"
RUN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
HIT_THRESHOLD = 0.8
PREDICTION_FIELDS = ("set", "src_id", "x", "y", "width", "height")


def split_key(key):
    set_name, src_id = key.split("/")
    return set_name, src_id


@cache
def images():
    """Every image in every set, in set then manifest order: dicts with key, set, src_id and the manifest's columns."""
    out = []
    for set_name, set_dir in SETS.items():
        with open(set_dir / "sample_selection.tsv") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                out.append({**row, "key": f"{set_name}/{row['src_id']}", "set": set_name})
    return out


def image_keys(sets=None):
    return [im["key"] for im in images() if sets is None or im["set"] in sets]


def subset_keys(n, sets=None):
    """A fixed, evenly spread subset of n images (every k-th, so spread across sets and buckets)."""
    keys = image_keys(sets)
    return keys[:: max(1, len(keys) // n)][:n]


def original_path(key):
    set_name, src_id = split_key(key)
    return SETS[set_name] / "originals" / f"{src_id}_uncropped.jpg"


def label_path(key):
    set_name, src_id = split_key(key)
    return SETS[set_name] / "labels" / f"{src_id}_cropinfo.txt"


def read_box(path):
    x, y, w, h = (int(v) for v in path.read_text().strip().split(","))
    return x, y, w, h


def read_label(key):
    """The labelled crop (x, y, width, height), or None if the image hasn't been labelled."""
    path = label_path(key)
    return read_box(path) if path.exists() else None


def read_predictions(path):
    """{key: (x, y, width, height)} from a predictions.tsv."""
    with open(path) as f:
        return {
            f"{r['set']}/{r['src_id']}": tuple(int(r[k]) for k in PREDICTION_FIELDS[2:])
            for r in csv.DictReader(f, delimiter="\t")
        }


def write_predictions(path, predictions):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(PREDICTION_FIELDS)
        for key, box in predictions.items():
            writer.writerow([*split_key(key), *box])


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def evaluate(predictions, keys=None):
    """
    Return ({key: iou} for the labelled images, [labelled keys with no prediction],
    [keys with no label]) over `keys` (default: all images).
    """
    scores, missing, unlabelled = {}, [], []
    for key in keys or image_keys():
        label = read_label(key)
        if label is None:
            unlabelled.append(key)
        elif key not in predictions:
            missing.append(key)
            scores[key] = 0.0
        else:
            scores[key] = iou(predictions[key], label)
    return scores, missing, unlabelled


def _stats(values):
    hits = sum(v >= HIT_THRESHOLD for v in values)
    n = len(values)
    return {"mean_iou": sum(values) / n if n else None, "hit_rate": hits / n if n else None, "hits": hits, "n": n}


def summarise(scores, missing, unlabelled):
    by_set = {}
    for set_name in SETS:
        values = [v for k, v in scores.items() if split_key(k)[0] == set_name]
        if values:
            by_set[set_name] = _stats(values)
    return {
        **_stats(list(scores.values())),
        "hit_threshold": HIT_THRESHOLD,
        "missing": len(missing),
        "unlabelled": len(unlabelled),
        "by_set": by_set,
    }


def format_summary(summary):
    def line(name, s):
        hits = f"{100 * s['hit_rate']:.1f}% ({s['hits']}/{s['n']})"
        return f"{name:8s} mean IoU {s['mean_iou']:.3f}, IoU >= {HIT_THRESHOLD}: {hits}"

    lines = [line("all", summary)] + [line(name, s) for name, s in summary["by_set"].items()]
    if summary["missing"]:
        lines.append(f"missing predictions (scored as 0): {summary['missing']}")
    if summary["unlabelled"]:
        lines.append(f"not scored (no label yet): {summary['unlabelled']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("predictions", type=Path)
    args = parser.parse_args()
    path = args.predictions / "predictions.tsv" if args.predictions.is_dir() else args.predictions
    if not path.is_file():
        parser.error(f"{path} doesn't exist")
    predictions = read_predictions(path)
    print(format_summary(summarise(*evaluate(predictions, list(predictions)))))


if __name__ == "__main__":
    main()
