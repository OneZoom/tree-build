"""
Shared argparse/logging helpers for standalone CLI scripts.
"""

import logging


def add_common_args(parser):
    """Add the verbosity/quiet arguments shared by standalone CLI scripts."""
    parser.add_argument(
        "-v",
        "--verbosity",
        action="count",
        default=0,
        help="How much information to print: use multiple times for more info",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=0,
        help="Do not log warnings (-q) or errors (-qq)",
    )


def setup_logging(args):
    log_level = "WARN"
    if args.quiet > 0:
        log_level = "ERROR"
        if args.quiet > 1:
            log_level = "CRITICAL"
            if args.quiet > 2:
                log_level = logging.CRITICAL + 1
    else:
        if args.verbosity > 0:
            log_level = "INFO"
        if args.verbosity > 1:
            log_level = "DEBUG"
    logging.basicConfig(level=log_level)
    return log_level
