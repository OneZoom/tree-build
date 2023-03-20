'''
Format a newick tree with indentation to make it more human readable
'''

'''
For example, if the input tree is:
(Tupaia_tana:8.5,(Tupaia_picta:8.0,(Tupaia_montana:7.0,Tupaia_splendidula:7.0):1.0):0.5):4.5;
The output is:
(
  Tupaia_tana:8.5,
  (
    Tupaia_picta:8.0,
    (
      Tupaia_montana:7.0,
      Tupaia_splendidula:7.0
    ):1.0
  ):0.5
):4.5;
'''

import argparse
import re
import sys

__author__ = "David Ebbo"

whole_token_regex = re.compile('[^(),;]+')

def format(newick_tree, output_stream, indent_spaces=2):

    indent_string = ' ' * indent_spaces

    index = 0
    depth = 0

    while index < len(newick_tree):

        if newick_tree[index] == '(':
            index += 1
            output_stream.write(indent_string * depth)
            output_stream.write('(\n')
            depth += 1
            continue

        closed_brace = newick_tree[index] == ')'
        if closed_brace:
            index += 1
            depth -= 1
            output_stream.write('\n')
            output_stream.write(indent_string * depth)
            output_stream.write(')')

        if match_full_name := whole_token_regex.match(newick_tree, index):
            index = match_full_name.end()
            if not closed_brace:
                output_stream.write(indent_string * depth)
            output_stream.write(match_full_name.group())

        if newick_tree[index] == ',':
            output_stream.write(newick_tree[index] + '\n')
            index += 1

        if newick_tree[index] == ';':
            output_stream.write(newick_tree[index] + '\n')
            break

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('treefile', type=argparse.FileType('r'), nargs='?', default=sys.stdin, help='The tree file in newick format')
    parser.add_argument('outputfile', type=argparse.FileType('w'), nargs='?', default=sys.stdout, help='The output tree file')
    parser.add_argument('--indent_spaces', '-i', default=2, type=int, help='the number of spaces for each indentation level')
    args = parser.parse_args()
    format(args.treefile.read(), args.outputfile, args.indent_spaces)

if __name__ == '__main__':
    main()