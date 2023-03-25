'''
Generate test files that are a filtered subset of the full files, targeted at a specific taxon.
'''

import argparse
import csv
import gzip
import logging
import os
import sys

from oz_tree_build.newick.extract_trees import get_taxon_subtree_from_newick_file
from oz_tree_build.newick.newick_parser import parse_tree

'''
Helper to perform caching of filtered files.
'''
def generate_and_cache_filtered_file(original_file, taxon, processing_function, *args):
    dir = os.path.dirname(original_file)
    file_name = os.path.basename(original_file)

    # Include the taxon in the new file name
    # e.g. '/foo/bar.csv.gz' --> '/foo/Mammalia_bar.csv.gz'
    taxon_filtered_file = os.path.join(dir, f"{taxon}_{file_name}")

    # Check if we already have a filtered file with the matching timestamp
    if os.path.exists(taxon_filtered_file) and os.path.getmtime(taxon_filtered_file) == os.path.getmtime(original_file):
        logging.info(f"Using cached file {taxon_filtered_file}")
        return taxon_filtered_file

    logging.info(f"Generating file {taxon_filtered_file}")

    # Call the processing function to generate the filtered file
    processing_function(original_file, taxon_filtered_file, taxon, *args)

    # Set the timestamp of the filtered file to match the original file
    os.utime(taxon_filtered_file, (os.path.getatime(original_file), os.path.getmtime(original_file)))

    logging.info(f"Finished generating file {taxon_filtered_file}")

    return taxon_filtered_file

def generate_filtered_newick(newick_file, filtered_newick_file, taxon):
    tree_string = get_taxon_subtree_from_newick_file(newick_file, taxon)

    with open(filtered_newick_file, 'wt', encoding="utf-8") as f:
        f.write(tree_string)

def generate_filtered_taxonomy_file(taxonomy_file, filtered_taxonomy_file, taxon, filtered_newick_file):
    with open(filtered_newick_file) as f:
        filtered_tree_string = f.read()

    # Get the set of OTT ids from the filtered tree
    otts = {node['ott'] for node in parse_tree(filtered_tree_string)}
    
    with open(taxonomy_file, 'rt',  encoding="utf-8") as input_taxonomy:
        with open(filtered_taxonomy_file, 'wt', encoding="utf-8") as filtered_taxonomy:
            for i, line in enumerate(input_taxonomy):
                # Always copy the header
                if i == 0:
                    filtered_taxonomy.write(line)
                    continue

                # The ott id is the first column (known as the "uid" in the tsv file)
                fields = line.split("\t")
                ott = fields[0]

                # Only include lines that have an ott id in the filtered tree
                if ott in otts:
                    filtered_taxonomy.write(line)


def generate_filtered_eol_id_file(eol_id_file, filtered_eol_id_file, taxon, filtered_taxonomy_file):
    sources = {'ncbi', 'if', 'worms', 'irmng', 'gbif'}
    source_ids = { source: set() for source in sources }

    with open(filtered_taxonomy_file, 'rt', encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter='\t')
        for OTTrow in reader:
            sourceinfo = OTTrow['sourceinfo']
            for srcs in sourceinfo.split(","):
                src, id = srcs.split(':',1)
                if src in sources:
                    source_ids[src].add(id)

    eol_sources = {'676': 'ncbi', '459': 'worms', '767': 'gbif'}
    with gzip.open(eol_id_file, "rt") as eol_f:
        with gzip.open(filtered_eol_id_file, 'wt', encoding="utf-8") as filtered_eol_f:
            for i, line in enumerate(eol_f):
                # Always copy the header
                if i == 0:
                    filtered_eol_f.write(line)
                    continue

                fields = line.split(",")

                # Ignore it if it's not one of the known sources
                if not fields[2] in eol_sources:
                    continue

                # Only include it if we saw that id in the taxonomy file
                if fields[1] in source_ids[eol_sources[fields[2]]]:
                    filtered_eol_f.write(line)

    logging.info(f"Found {len(source_ids['ncbi'])} NCBI ids, {len(source_ids['if'])} IF ids, {len(source_ids['worms'])} WoRMS ids, {len(source_ids['irmng'])} IRMNG ids, {len(source_ids['gbif'])} GBIF ids")

def generate_all_filtered_files(
        taxon, newick_file, taxonomy_file, eol_id_file, wikidata_dump_file,
        wikipedia_sql_dump_file, wikipedia_totals_bz2_pageviews):

    filtered_newick_file = generate_and_cache_filtered_file(newick_file, taxon, generate_filtered_newick)

    filtered_taxonomy_file = generate_and_cache_filtered_file(taxonomy_file, taxon, generate_filtered_taxonomy_file, filtered_newick_file)

    filtered_eol_id_file = generate_and_cache_filtered_file(eol_id_file, taxon, generate_filtered_eol_id_file, filtered_taxonomy_file)



def main():
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('Taxon', 
        help='The taxon for which to generate test files')
    parser.add_argument('Tree', 
        help='The newick format tree to use')
    parser.add_argument('OpenTreeTaxonomy', 
        help='The 325.6 MB Open Tree of Life taxonomy.tsv file, from http://files.opentreeoflife.org/ott/')
    parser.add_argument('EOLidentifiers', 
        help='The gzipped 450 MB EOL identifiers file, from https://opendata.eol.org/dataset/identifiers-csv-gz')
    parser.add_argument('wikidataDumpFile', nargs="?", 
        help='The b2zipped >4GB wikidata JSON dump, from https://dumps.wikimedia.org/wikidatawiki/entities/ (latest-all.json.bz2) ')
    parser.add_argument('wikipediaSQLDumpFile', nargs="?",
        help='The gzipped >1GB wikipedia -latest-page.sql.gz dump, from https://dumps.wikimedia.org/enwiki/latest/ (enwiki-latest-page.sql.gz) ')
    parser.add_argument('wikipedia_totals_bz2_pageviews', nargs='*',
        help='One or more b2zipped "totals" pageview count files, from https://dumps.wikimedia.org/other/pagecounts-ez/merged/ (e.g. pagecounts-2016-01-views-ge-5-totals.bz2, or pagecounts*totals.bz2)')
    args = parser.parse_args()

    generate_all_filtered_files(args.Taxon, args.Tree, args.OpenTreeTaxonomy, args.EOLidentifiers,
                                args.wikidataDumpFile, args.wikipediaSQLDumpFile, args.wikipedia_totals_bz2_pageviews)

if __name__ == '__main__':
    main()