# BSD 3-Clause License

# Copyright (c) 2025, Jonathan David Duke

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.

# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.

# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


import json
import os
import sys
import gc
import numpy as np
import datetime

from dated_complete_tree import tree_loading
from dated_complete_tree import tree_labelling
from dated_complete_tree import tree_fixing
from dated_complete_tree import tree_dating
from dated_complete_tree import tree_metrics

import argparse
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(filename="main.log", filemode="w", force=True, level=logging.ERROR)


def generate_trees(args):
    if not os.path.exists(args.output_folder):
        os.makedirs(args.output_folder)

    sys.setrecursionlimit(10000)

    rng = np.random.default_rng(seed=1)
    date_interpolation_rng = np.random.default_rng(seed=1)
    date_source_rng = np.random.default_rng(seed=1)

    #####################################################################################################################
    # Load and prune tree

    # Load metadata for tree from Open Tree and Chronosynth
    with open(args.date_cache) as f:
        dates = json.load(f)
    phylogeny_nodes, taxa = tree_loading.load_metadata(
        date_cache=None,
        annotations=args.annotations,
        taxonomy=args.taxonomy,
    )

    # Create ETE3 tree structure for entire Open Tree of Life, with my annotations
    whole_tre_unmodified = tree_loading.build_and_annotate_tree(phylogeny_nodes, taxa, tree_filename=args.supertree)

    tree_fixing.strip_birds(whole_tre_unmodified)
    tree_fixing.strip_turtles(whole_tre_unmodified)

    rng = np.random.default_rng(seed=1)

    tree_fixing.remove_subspecies(whole_tre_unmodified, rng)
    tree_fixing.impute_species_into_empty_taxa(whole_tre_unmodified)

    tree_fixing.fix_taxonomy_ordering(whole_tre_unmodified)

    tree_labelling.add_anc_ranks(whole_tre_unmodified)
    tree_labelling.add_desc_ranks(whole_tre_unmodified)

    tree_fixing.forced_taxa_moves(whole_tre_unmodified)

    if args.pd_clades:
        topo_pd_clades = [cld.strip() for cld in list(open(args.pd_clades))]
        topo_pd_dict = {}
        topo_dates_dict = {}
        topo_spp_dict = {}
        for clade in topo_pd_clades:
            topo_pd_dict[clade] = []
            topo_dates_dict[clade] = []
            topo_spp_dict[clade] = []

        if args.num_date_samples > 0:
            both_pd_clades = [cld.strip() for cld in list(open(args.pd_clades))]
            both_pd_dict = {}
            both_dates_dict = {}
            both_spp_dict = {}
            for clade in both_pd_clades:
                both_pd_dict[clade] = []
                both_dates_dict[clade] = []
                both_spp_dict[clade] = []

    if args.compute_ed:
        topo_ed_scores = {}
        if args.num_date_samples > 0:
            both_ed_scores = {}

    itr_start = datetime.datetime.now()

    for n in range(args.num_trees):
        print("Tree number", n+1, "/ projected end time:", itr_start + args.num_trees*(datetime.datetime.now() - itr_start)/n if n > 0 else "first iteration, no estimate yet")

        # Copy tree - we will change the copy, and keep the original unchanged so we can restore it next iteration without
        # reloading everything
        whole_tre = whole_tre_unmodified.copy()

        #####################################################################################################################
        # Fix topology

        # First, do labelling for steps 1-3:
        #  - 1-2 are independent of each other; step 3 collects up nodes not labelled in 1-2.
        #  - tree is only labelled at this stage; modifications are made in tree_fixing functions.
        genus_dict = {}       # step 1, nodes below genus nodes
        nmp_genus_dict = {}   # step 2, non-monophyletic genera
        tree_labelling.populate_genus_dict(whole_tre, genus_dict, nmp_genus_dict, None)

        tofix_dict = {}       # step 3, all other nodes from taxonomy (not phylogenies) to
                              # be moved to a suitable place in the tree, such that we
                              # generated a plausible hypothetical tree
        tree_labelling.populate_tofix_dict(whole_tre, tofix_dict, nmp_genus_dict)

        # Second, fix the topology based on the labels.
        # Fix steps 1 and 2.
        tree_fixing.fix_polyphyly(genus_dict, rng)
        tree_fixing.fix_polyphyly(nmp_genus_dict, rng)

        tree_fixing.remove_nonspecies_leaves(whole_tre)

        # Find and label backbone for step 3, after steps 1 an 2 already fixed.
        tree_labelling.populate_tofix_bkb(whole_tre, tofix_dict, [])
        fix_dict = tree_labelling.process_tofix_bkb(tofix_dict)

        # Finally, fix step 3.
        tree_fixing.fix_polyphyly(fix_dict, rng, expand_parent_backbones=True)

        tree_fixing.remove_nonspecies_leaves(whole_tre)

        # Last of all, polytomy resolution.
        tree_fixing.fix_all_polytomies(whole_tre, rng)

        # Remove one-child nodes. Gives a fully bifurcating tree.
        whole_tre = tree_fixing.delete_one_child_nodes(whole_tre)

        #####################################################################################################################
        # Assign and interpolate median dates

        # Assign dates
        tree_dating.assign_dates(whole_tre, dates)

        # Date cleaning to ensure time consistency down the tree
        tree_dating.label_older_descendants(whole_tre)
        tree_dating.dq_date_removal(whole_tre)

        # Date imputation
        tree_dating.date_labelling(whole_tre)
        if args.use_birth_model:
            tree_dating.impute_missing_dates(whole_tre, use_birth_model=True, rng=date_interpolation_rng)
        else:
            tree_dating.impute_missing_dates(whole_tre, l=0.25)

        # All nodes now dated - set dists in ete and write out tree.
        tree_dating.compute_branch_lengths(whole_tre)
        tree_dating.write_tree_with_branch_lengths(whole_tre, filename="%s/%s_topo_sample_%d.tre" % (args.output_folder, args.output_tree_filename, n+1))

        if args.compute_ed:
            tree_metrics.compute_ed_scores(whole_tre, topo_ed_scores)

        if args.pd_clades:
            tree_metrics.compute_pd(whole_tre)
            tree_metrics.save_pd_for_clades(whole_tre, topo_pd_clades, topo_pd_dict, topo_dates_dict, topo_spp_dict)

        # Now do date sampling, if desired
        for s in range(args.num_date_samples):
            print("  Tree number", n+1, "; Date sample", s+1)
            for node in whole_tre.traverse(strategy="preorder"):
                # reset all dates
                node.props["date"] = None
                node.props["imputed_date"] = False
                node.props["imputation_type"] = 0

            # Assign dates
            tree_dating.assign_dates(whole_tre, dates, sample_dates=True, rng=date_source_rng)

            # Date cleaning to ensure time consistency down the tree
            tree_dating.label_older_descendants(whole_tre)
            tree_dating.dq_date_removal(whole_tre)

            # Date imputation
            tree_dating.date_labelling(whole_tre)
            if args.use_birth_model:
                tree_dating.impute_missing_dates(whole_tre, use_birth_model=True, rng=date_interpolation_rng)
            else:
                tree_dating.impute_missing_dates(whole_tre, l=0.25)

            # All nodes now dated - set dists in ete and write out tree.
            tree_dating.compute_branch_lengths(whole_tre)
            tree_dating.write_tree_with_branch_lengths(whole_tre, filename="%s/%s_both_sample_%d.tre" % (args.output_folder, args.output_tree_filename, n*args.num_date_samples+s+1))

            if args.compute_ed:
                tree_metrics.compute_ed_scores(whole_tre, both_ed_scores)

            if args.pd_clades:
                tree_metrics.compute_pd(whole_tre)
                tree_metrics.save_pd_for_clades(whole_tre, both_pd_clades, both_pd_dict, both_dates_dict, both_spp_dict)

        del whole_tre
        gc.collect()


    if args.compute_ed:
        print("Writing out ED score distributions for all species (takes ~5 minutes)")
        tree_metrics.write_ed_scores("%s/%s_topo_ed_scores.txt" % (args.output_folder, args.output_tree_filename), topo_ed_scores)

        if args.num_date_samples > 0:
            tree_metrics.write_ed_scores("%s/%s_both_ed_scores.txt" % (args.output_folder, args.output_tree_filename), both_ed_scores)

    if args.pd_clades:
        tree_metrics.write_pd_dists("%s/%s_topo" % (args.output_folder, args.output_tree_filename), topo_pd_dict, topo_dates_dict, topo_spp_dict)

        if args.num_date_samples > 0:
            tree_metrics.write_pd_dists("%s/%s_both" % (args.output_folder, args.output_tree_filename), both_pd_dict, both_dates_dict, both_spp_dict)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate a set of dated trees of all life, based on the Open Tree of Life and Chronosynth. "
            "Optionally, also generate evolutionary distinctiveness scores for the trees"
        )
    )

    parser.add_argument("--num_trees",
                        help="How many trees to generate. Default: 1",
                        type=int,
                        default=1)

    parser.add_argument("--num_date_samples",
                        help="How many times to sample a set of dates for each tree (in addition to the tree using median dates). Default: 0",
                        type=int,
                        default=0)

    parser.add_argument("--output_folder",
                        help="Path of folder where output trees will be written in Newick format, Default: output",
                        default="output")

    parser.add_argument("--output_tree_filename",
                        help="Filename for output trees, e.g. the default 'dated_tree' would result in trees named 'dated_tree_topo_sample_1', '..._2' etc.",
                        default="dated_tree")

    parser.add_argument("--supertree",
                        help="Path of the labelled_supertree_ottnames.tre file from the Open Tree of Life. Default: opentree16.1_tree/labelled_supertree/labelled_supertree_ottnames.tre",
                        default="opentree16.1_tree/labelled_supertree/labelled_supertree_ottnames.tre")

    parser.add_argument("--date_cache",
                        help="Path of the date cache generated by Chronosynth. Default: chronosynth_date_info/node_ages.json",
                        default="chronosynth_date_info/node_ages.json")

    parser.add_argument("--annotations",
                        help="Path of the annotations.json file from the Open Tree of Life. Default: opentree16.1_tree/annotations.json",
                        default="opentree16.1_tree/annotations.json")

    parser.add_argument("--taxonomy",
                        help="Path of the taxonomy.tsv file from the Open Tree Taxonomy. Default: ott3.7.3/taxonomy.tsv",
                        default="ott3.7.3/taxonomy.tsv")

    parser.add_argument("--use_birth_model",
                        help="Flag: whether use the date interpolation method based on a birth model, rather than the EQS-LS method. Default: False",
                        action="store_true")

    parser.add_argument("--pd_clades",
                        help="Path of a text file containing a list of node names (one on each line) for which to output PD estimates. Default: None",
                        default=None)

    parser.add_argument("--compute_ed",
                        help="Flag: whether to compute a distribution of ED scores. A csv file summarising the scores will be placed in the output folder. Default: False",
                        action="store_true")

    args = parser.parse_args()
    generate_trees(args)


if __name__ == "__main__":
    main()
