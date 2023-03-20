'''
Look for regex matches within files with very long lines (unlike grep, which matches entire lines).
The challenge is that the regex engine can't see the entire file at once, so we need to read the file in
chunks and stitch the chunks together before passing them to the regex engine.
'''

import argparse
import re
import sys

__author__ = "David Ebbo"

def chunks_from_file(f, chunk_size):
    while chunk := f.read(chunk_size):
        yield chunk

def get_matches(chunk_iterator, regex, window_size):
    overall_index = 0

    chunk = next(chunk_iterator)

    # The last window_size characters from the previous chunk, used to stitch together matches that span chunks
    pre_string = ""

    while chunk:
        try:
            next_chunk = next(chunk_iterator)
        except StopIteration:
            next_chunk = ""

        # Include the next chunk in the current chunk, so that we can find matches that span chunks
        # This assumes that the chunk size is larger than any match we want to find
        current_string = chunk + next_chunk

        for m in re.finditer(regex, current_string):
            # If the match is in the next chunk, we'll find it in the next iteration
            if m.start() >= len(chunk):
                break

            # Come up with how much we want to display around the match
            window_start = max(0, m.start() - window_size)
            window_end = min(len(current_string), m.end() + window_size)

            # If the match is at the start of the chunk, we may need to get some characters from the previous chunk
            string_to_return = current_string[window_start:window_end]
            chars_needed_from_pre_string = window_size - (m.start() - window_start)
            if chars_needed_from_pre_string > 0:
                string_to_return = pre_string[-chars_needed_from_pre_string:] + string_to_return

            yield (overall_index + m.start(), string_to_return)
        
        overall_index += len(chunk)

        # Save the last window_size characters from the current chunk
        pre_string = chunk[-window_size:]

        chunk = next_chunk

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('regex', help='The expression to search for')
    parser.add_argument('file', type=argparse.FileType('r'), nargs='?', default=sys.stdin, help='The input file')
    parser.add_argument('--window_size', '-w', type=int, default=100, help='the number of characters to display before and after each match')
    parser.add_argument('--chunk_size', '-c', type=int, default=10000, help='the size of the chunks to read from the file')
    args = parser.parse_args()

    for index, match in get_matches(chunks_from_file(args.file, args.chunk_size), args.regex, args.window_size):
        print(f"{index}: {match}")

if __name__ == '__main__':
    main()