"""
Run a cropper from oz_tree_build.images.image_cropping (any name in its CROPPERS) over
the image sets in evaluate.py, store the run in runs/NAME/, and score it.

Usage: python data/crop_experiment/run_cropper.py CROPPER [--name NAME] [--force]
           [--subset N] [--set extant|extinct] [--config APPCONFIG]

Croppers are run as the pipeline runs them, through crop_with_details(), and made with
--config (default: the repo root's appconfig.ini, which is gitignored), which holds
the API keys: [azure_vision] for Azure, [openrouter] key for the OpenRouter-based
croppers. A remote cropper's calls go through
request_cache.py, so reruns are free and reproducible, and keys are only needed for
calls that aren't cached.

Each run directory holds:
  predictions.tsv  the crop for each image (set, src_id, x, y, width, height)
  run.json         cropper, timing, git commit, problems found, and usage (requests,
                   tokens, cost, how crops were reached) from the croppers' reports
  results.json     evaluate.summarise's scores, plus each image's IoU
  details.json     (croppers that report boxes) the boxes, for the run viewer
"""

import argparse
import datetime
import json
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from functools import reduce
from operator import add
from pathlib import Path

import evaluate
import request_cache

from oz_tree_build.images.image_cropping import CROPPERS, Usage, make_cropper
from oz_tree_build.utilities.db_helper import read_config

EXPERIMENT_DIR = Path(__file__).resolve().parent
DEFAULT_APPCONFIG = EXPERIMENT_DIR.parent.parent / "appconfig.ini"
PROJECT_TO_IMAGES = 300_000


def usage_summary(cropper, results):
    """What the run's crops cost and how they were reached, from what the cropper reported; None if it made no calls."""
    usages = [r.usage for r in results]
    if not any(u.requests for u in usages):
        return None

    def mean(field):
        values = [getattr(u, field) for u in usages if getattr(u, field) is not None]
        return round(sum(values) / len(values), 3) if values else None

    costs = [u.cost_usd for u in usages if u.cost_usd is not None]
    total = reduce(add, usages, Usage())
    out = {
        "model": getattr(cropper, "model", None),
        "requests": total.requests,
        "mean_input_tokens": mean("input_tokens"),
        "mean_output_tokens": mean("output_tokens"),
        "mean_reasoning_tokens": mean("reasoning_tokens"),
        "total_cost_usd": round(sum(costs), 6) if costs else None,
        "cost_is_list_price": total.cost_is_list_price,
    }
    if costs:
        out["cost_per_image_usd"] = round(sum(costs) / len(costs), 8)
        out[f"projected_cost_for_{PROJECT_TO_IMAGES}_usd"] = round(sum(costs) / len(costs) * PROJECT_TO_IMAGES, 2)
    flags = sorted({k for r in results for k, v in r.details.items() if isinstance(v, bool)})
    if flags:
        out["flags"] = {k: sum(bool(r.details.get(k)) for r in results) for k in flags}
    return {k: v for k, v in out.items() if v is not None}


def git_commit():
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=EXPERIMENT_DIR, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=EXPERIMENT_DIR, text=True).strip()
        return commit + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cropper", choices=sorted(CROPPERS))
    parser.add_argument("--name", help="run name (default: the cropper's name)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing run of the same name")
    parser.add_argument("--subset", type=int, metavar="N", help="only run on a fixed, evenly spread subset of N images")
    parser.add_argument("--set", action="append", choices=sorted(evaluate.SETS), help="only these image sets")
    parser.add_argument("--config", type=Path, default=DEFAULT_APPCONFIG, help="appconfig.ini with the API keys")
    args = parser.parse_args()

    name = args.name or args.cropper
    if not evaluate.RUN_NAME_RE.match(name):
        parser.error(f"invalid run name {name!r}")
    run_dir = evaluate.RUNS_DIR / name
    if run_dir.exists() and not args.force:
        parser.error(f"run {name!r} already exists (use --force to overwrite)")

    keys = evaluate.subset_keys(args.subset, args.set) if args.subset else evaluate.image_keys(args.set)
    images = {im["key"]: im for im in evaluate.images()}
    cropper = make_cropper(args.cropper, read_config(args.config) if args.config.exists() else None)
    if cropper.transport is not None:
        cropper.transport = request_cache.CachedTransport(cropper.transport)
    started = datetime.datetime.now().astimezone()
    t0 = time.perf_counter()

    def crop(key):
        try:
            return cropper.crop_with_details(None, evaluate.original_path(key), images[key].get("name") or None)
        except Exception as e:
            return e

    predictions, failures, not_square, out_of_bounds, details, results = {}, {}, [], [], {}, []
    with ThreadPoolExecutor(max_workers=cropper.concurrency) as pool:
        for i, (key, result) in enumerate(zip(keys, pool.map(crop, keys)), 1):
            if i % 50 == 0:
                print(f"  {i}/{len(keys)}")
            if isinstance(result, Exception):
                failures[key] = f"{type(result).__name__}: {str(result)[:300]}"
                continue
            x, y, w, h = result.box.as_tuple()
            img_w, img_h = int(images[key]["width"]), int(images[key]["height"])
            if w != h:
                not_square.append(key)
            if x < 0 or y < 0 or x + w > img_w or y + h > img_h:
                out_of_bounds.append(key)
            predictions[key] = (x, y, w, h)
            results.append(result)
            if result.details.get("boxes"):
                details[key] = {"boxes": result.details["boxes"]}
    seconds = time.perf_counter() - t0

    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    evaluate.write_predictions(run_dir / "predictions.tsv", predictions)
    run_info = {
        "name": name,
        "cropper": args.cropper,
        "subset": args.subset,
        "sets": args.set or sorted(evaluate.SETS),
        "n_images": len(keys),
        "started": started.isoformat(timespec="seconds"),
        "seconds": round(seconds, 2),
        "seconds_per_image": round(seconds / len(keys), 4),
        "git_commit": git_commit(),
        "failures": failures,
        "not_square": not_square,
        "out_of_bounds": out_of_bounds,
    }
    usage = usage_summary(cropper, results)
    if usage:
        run_info["usage"] = usage
    (run_dir / "run.json").write_text(json.dumps(run_info, indent=2) + "\n")
    if details:
        (run_dir / "details.json").write_text(json.dumps(details) + "\n")

    scores, missing, unlabelled = evaluate.evaluate(predictions, keys)
    summary = evaluate.summarise(scores, missing, unlabelled)
    results = {**summary, "per_image": {k: round(v, 4) for k, v in scores.items()}}
    (run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")

    print(f"run {name!r} ({seconds:.1f}s, {1000 * seconds / len(keys):.0f}ms/image)")
    print(evaluate.format_summary(summary))
    for label, items in (("failed", failures), ("not square", not_square), ("out of bounds", out_of_bounds)):
        if items:
            print(f"{label}: {len(items)}")
    if failures:
        print("first failures:", *[f"  {k}: {v}" for k, v in list(failures.items())[:5]], sep="\n")
    for key, value in run_info.get("usage", {}).items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
