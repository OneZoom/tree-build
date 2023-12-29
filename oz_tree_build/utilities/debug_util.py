import logging
import sys


# Helper function to set up logging
def parse_args_and_add_logging_switch(parser):
    parser.add_argument(
        "--verbosity",
        "-v",
        action="count",
        default=0,
        help="verbosity level: output extra non-essential info",
    )

    args = parser.parse_args()

    if args.verbosity == 0:
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    elif args.verbosity == 1:
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    elif args.verbosity == 2:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    return args
