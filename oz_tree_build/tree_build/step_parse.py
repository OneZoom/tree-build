# https://github.com/etetoolkit/ete/blob/ete4/ete4/core/tree.pyx
# https://github.com/etetoolkit/ete/blob/ete4/ete4/parser/newick.pyx
import glob
import logging
import os.path

import ete4

from .step_graft import decypher_inclusion_syntax, remove_exclusions
from .token_to_oz_tree_file_mapping import token_to_file_map

logger = logging.getLogger(__name__)

NWK_READ_PARSER = 1


def parse_ot_orphans(orphan_dir, inclusions):
    """
    Load orphan OpenTree subtrees from ``orphan_dir`` that match the given
    inclusion labels.

    ``orphan_dir`` is expected to contain ``<ott>.nwk`` files, one per OpenTree
    subtree that lives outside the main OpenTree synthesis (the "orphan"
    pieces). Each ``inclusions`` label is parsed for its base OTT
    (see ``decypher_inclusion_syntax``); if a file named
    ``<base_ott>.nwk`` exists, it is loaded and returned, keyed by the
    *original* inclusion label so callers can pass the result straight to
    ``graft_tree``.

    Any ``excluded_otts`` carried by the inclusion syntax are pruned from the
    loaded subtree via ``remove_exclusions`` before it is returned. Orphan
    files that don't correspond to any requested inclusion are skipped, and
    inclusions with no matching orphan file are silently absent from the
    result.
    """
    # Organise inclusions by base_ott (as string)
    start_otts = {}
    for i in inclusions:
        r = decypher_inclusion_syntax(i)
        start_otts[str(r["base_ott"])] = r

    # Find orphan trees that match inclusion points
    out_trees = {}
    for orphan_path in glob.glob(os.path.join(orphan_dir, "*.nwk")):
        node_ott = os.path.splitext(os.path.basename(orphan_path))[0]
        if node_ott not in start_otts:
            continue
        r = start_otts[node_ott]
        del start_otts[node_ott]

        sub_t = ete4.Tree(orphan_path, parser=NWK_READ_PARSER)
        remove_exclusions(sub_t, r["excluded_otts"])
        out_trees[r["orig_name"]] = sub_t
    return out_trees


def parse_bespoke_trees(bespoke_dir, base_name="Base.PHY"):
    """
    Load the base tree and every hand-curated ("bespoke") subtree referenced
    by ``token_to_file_map`` from ``bespoke_dir``.

    Returns a ``(base_t, bespoke_t)`` tuple:
      - ``base_t`` is the tree parsed from ``<bespoke_dir>/<base_name>`` and
        forms the trunk that everything else hangs off.
      - ``bespoke_t`` is a dict keyed by ``"<TOKEN>@"`` (matching the
        inclusion syntax used inside ``base_t``) mapping to the parsed
        subtree. For each token, the entry in ``token_to_file_map`` may
        override the subtree's root name (``taxon``) and the length of the
        edge connecting it to its parent (``edge_length``).

    The result is suitable for passing straight to ``graft_tree`` as the
    ``additional_trees`` argument. Tokens whose file is missing from
    ``bespoke_dir`` are logged as errors and omitted from ``bespoke_t``
    rather than raising.
    """
    base_t = ete4.Tree(os.path.join(bespoke_dir, base_name), parser=NWK_READ_PARSER)
    bespoke_t = {}
    for key, x in token_to_file_map.items():
        key = key + "@"
        sub_path = os.path.join(bespoke_dir, x["file"])
        if not os.path.exists(sub_path):
            logger.error(f"Sub-tree {x['file']} referenced in token_to_oz_tree_file_mapping missing")
            continue
        bespoke_t[key] = ete4.Tree(sub_path, parser=NWK_READ_PARSER)
        if x.get("taxon") is not None:
            bespoke_t[key].root.name = x["taxon"]
        if x.get("edge_length") is not None:
            bespoke_t[key].root.dist = x["edge_length"]
    return base_t, bespoke_t
