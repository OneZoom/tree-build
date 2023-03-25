'''
This script takes a Wikipedia JSON dump file and trims it down to only the
pages that are relevant to OneZoom.
'''

import argparse
import bz2
import json
import logging
import re
import sys
import time

match_taxa = {
    16521: 'taxon',
    310890: 'monotypic taxon',
    23038290: 'fossil taxon',
    713623: 'clade',
}
match_vernacular = {
    502895: 'common name',
    55983715: 'group of organisms known by one particular common name',
}

regexp_match = '|'.join([str(v) for v in list(match_taxa) + list(match_vernacular)])
quick_byte_match = re.compile('numeric-id":(?:{})\D'.format(regexp_match))


known_claims = { "P31", "P685", "P846", "P850", "P1391", "P5055", "P830", "P141", "P627", "P961" }

def enumerate_lines_from_bz2_file(filename):
    with bz2.open(filename, 'rt') as f:
        for line_num, line in enumerate(f):
            yield line_num, line

def enumerate_lines_from_plain_file(filename):
    with open(filename, 'rt') as f:
        for line_num, line in enumerate(f):
            yield line_num, line

def process_all_lines(line_enumerator, output_stream, language='en'):
    output_stream.write('[\n')
    first = True
    preserved_lines = 0

    sitelinks_key = f'{language}wiki'

    for line_num, line in line_enumerator:
        if (line_num > 0 and line_num % 100000 == 0):
            logging.info(f"Kept {preserved_lines} out of {line_num} processed lines ({preserved_lines / line_num * 100:.2f}%))")

        # if not(line.startswith('{"type":') and quick_byte_match.search(line)):
        if not line.startswith('{"type":'):
            continue

        preserved_lines += 1

        if not first:
            output_stream.write(',\n')
        first = False

        json_item = json.loads(line.rstrip().rstrip(","))

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

        # Set the separators to avoid spaces
        output_stream.write(json.dumps(json_item, separators=(',', ':')))

    output_stream.write('\n]\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verbosity', '-v', action='count', default=0, help='verbosity level: output extra non-essential info')
    parser.add_argument('wikipedia_file', help='The tree file in newick format')
    parser.add_argument('outputfile', type=argparse.FileType('w'), nargs='?', default=sys.stdout, help='The trimmed output file')
    args = parser.parse_args()

    if args.verbosity==0:
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    elif args.verbosity==1:
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    elif args.verbosity==2:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    start = time.time()

    if args.wikipedia_file.endswith('.bz2'):
        line_enumerator = enumerate_lines_from_bz2_file(args.wikipedia_file)
    else:
        line_enumerator = enumerate_lines_from_plain_file(args.wikipedia_file)

    process_all_lines(line_enumerator, args.outputfile)

    end = time.time()
    logging.debug("Time taken: {} seconds".format(end - start))

if __name__ == '__main__':
    main()