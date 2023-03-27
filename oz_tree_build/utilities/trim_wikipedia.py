'''
This script takes a Wikipedia JSON dump file and trims it down to only the
pages that are relevant to OneZoom.
'''

import argparse
import bz2
import gzip
import json
import logging
import sys
import time

from oz_tree_build.utilities.temp_helpers import *

known_claims = { "P31", "P685", "P846", "P850", "P1391", "P5055", "P830", "P141", "P627", "P961" }

def open_file_based_on_extension(filename, mode):
    # Open a file, whether it's compressed or not
    if filename.endswith('.bz2'):
        return bz2.open(filename, mode, encoding='utf-8')
    elif filename.endswith('.gz'):
        return gzip.open(filename, mode, encoding='utf-8')
    else:
        return open(filename, mode, encoding='utf-8')

def enumerate_lines_from_file(filename):
    with open_file_based_on_extension(filename, 'rt') as f:
        for line_num, line in enumerate(f):
            yield line_num, line

def process_all_lines(wikipedia_file, output_stream, language='en'):

    output_stream.write('[\n')
    preserved_lines = 0

    # We want all the vernacular lines to end up at the end of the file, so we
    # store them in a list. There are only a few hundred, so memory isn't
    # an issue.
    vernacular_lines = []

    sitelinks_key = f'{language}wiki'

    for line_num, line in enumerate_lines_from_file(wikipedia_file):
        if (line_num > 0 and line_num % 100000 == 0):
            logging.info(f"Kept {preserved_lines} out of {line_num-1} processed lines ({preserved_lines / line_num * 100:.2f}%))")

        if not(line.startswith('{"type":') and quick_byte_match.search(line)):
            continue

        json_item = json.loads(line.rstrip().rstrip(","))

        try:
            is_taxon, vernaculars = find_taxon_and_vernaculars(json_item)
        except KeyError:
            continue

        # If it's neither, ignore it
        if not is_taxon and not len(vernaculars) > 0:
            continue

        preserved_lines += 1

        # Remove things we don't need at all
        if 'descriptions' in json_item:
            del json_item['descriptions']
        if 'aliases' in json_item:
            del json_item['aliases']

        # Only keep the English labels
        if language in json_item['labels']:
            json_item['labels'] = {language: json_item['labels'][language]}
        else:
            json_item['labels'] = {}

        # Only keep the claims we care about
        json_item['claims'] = {k: v for k, v in json_item['claims'].items() if k in known_claims}

        # Only keep the sitelinks that end in "wiki", e.g. enwiki, dewiki, etc.
        # And among those, only keep the original value for the language we want, since the
        # rest is just needed to collect the language names into the bit field
        json_item['sitelinks'] = {k: v if k==sitelinks_key else {} for k, v in json_item['sitelinks'].items() if k.endswith('wiki')}

        # We set the separators to avoid spaces
        output_line = json.dumps(json_item, separators=(',', ':'))

        if is_taxon:
            # Write the line to the output file
            output_stream.write(output_line)
            output_stream.write(',\n')
        else:
            # If it's vernacular, we'll write it out at the end
            vernacular_lines.append(output_line)

    # Write out the vernacular lines
    logging.info(f"Writing {len(vernacular_lines)} vernacular lines at the end of the file")
    for line in vernacular_lines:
        output_stream.write(line)
        output_stream.write(',\n')

    output_stream.write(']\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verbosity', '-v', action='count', default=0, help='verbosity level: output extra non-essential info')
    parser.add_argument('wikipedia_file', help='The tree file in newick format')
    parser.add_argument('outputfile', help='The trimmed output file')
    args = parser.parse_args()

    if args.verbosity==0:
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    elif args.verbosity==1:
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    elif args.verbosity==2:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    start = time.time()

    with open(args.outputfile, 'wt') as output_stream:
        process_all_lines(args.wikipedia_file, output_stream)

    end = time.time()
    logging.debug("Time taken: {} seconds".format(end - start))

if __name__ == '__main__':
    main()