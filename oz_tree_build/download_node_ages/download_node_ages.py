"""
Populate node_ages.json by calling out to the OpenTree API via. chronosynth

Usage: download_node_ages node_ages.json

NB: The output is not based on the tree downloaded in other steps,
internally chronosynth will call out to the OpenTree API &
github.com/OpenTreeOfLife/phylesystem-1.

"""

import argparse
import json
import logging
import os
import os.path
import sys
import time

os.environ["CHRONOSYNTH_CONFIG_FILE"] = os.path.join(os.path.dirname(__file__), "chronosynth_config.ini")
os.environ["PEYOTL_CONFIG_FILE"] = os.path.join(os.path.dirname(__file__), "peyotl_config.ini")

import chronosynth.chronogram  # noqa: E402 - we need to set env first


def download_node_ages():
    dates = chronosynth.chronogram.build_synth_node_source_ages(fresh=True)

    # Remove sources, from dated_complete_tree/tree_loading.py
    sources_to_delete = set(["ot_1250@tree2"])
    deletions = []
    for ott_name in dates["node_ages"]:
        for i, source in enumerate(dates["node_ages"][ott_name]):
            if source["source_id"] in sources_to_delete:
                deletions.append((ott_name, i))

    deletions.sort(reverse=True)

    for ott_name, i in deletions:
        del dates["node_ages"][ott_name][i]
        if len(dates["node_ages"][ott_name]) == 0:
            del dates["node_ages"][ott_name]
    ####

    return dates


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--verbosity",
        "-v",
        action="count",
        default=0,
        help="verbosity level: output extra non-essential info",
    )
    parser.add_argument("output_path", help="Path to where output data should be saved")
    args = parser.parse_args()

    if args.verbosity == 0:
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    elif args.verbosity == 1:
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    elif args.verbosity == 2:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    start = time.time()

    with open(args.output_path, "w") as f:
        json.dump(download_node_ages(), f)

    end = time.time()
    logging.debug(f"Time taken: {end - start} seconds")


if __name__ == "__main__":
    main()
